"""Transactional Home requests. No network calls or payment effects in this module.

One existing Booking is the aggregate root; HomeVisit adds consent and household
instructions. Row locks serialize transitions, version checks reject stale screens,
and a per-actor command lock makes concurrent retries return one durable result.
"""
import hashlib
import json
import os
import re
import uuid
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select, insert, update, text, or_, and_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from models import User, CookProfile, Booking
from models.home_service import HomeVisit, HomeHelperPermission, HomeEvent, HomeCommand

CONSENT_VERSION = 'home-visit-v2'
CONSENT_TEXT = ('I agree to share these visit instructions and my service address with CookCredit '
                'and the helper assigned to this visit, so they can review and carry out my request. '
                'If I am arranging this for someone else, I have their permission to arrange it and share these details.')
PREFERENCES = {'allergies', 'provided_meal_instructions', 'easy_to_chew', 'label_meals',
               'storage_help', 'fragrance_free', 'customer_supplies', 'phone_help'}
CLEANING_TASKS = {'kitchen', 'dishes', 'bathroom', 'floors', 'laundry', 'general_tidy'}


class HomeError(Exception):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def fail(code, message, status=400):
    raise HomeError(code, message, status)


def strict_object(body, required, optional=()):
    if not isinstance(body, dict) or set(body) - set(required) - set(optional) or set(required) - set(body):
        fail('invalid_fields', 'Please check the required fields.')


def bounded_text(value, name, maximum, *, required=False):
    if not isinstance(value, str) or len(value) > maximum or (required and not value.strip()):
        fail('invalid_input', f'Please check {name}.')
    # Control characters break messages and logs; plain line breaks are allowed.
    if any(ord(c) < 32 and c not in '\n\t' for c in value):
        fail('invalid_input', f'Please check {name}.')
    return value.strip()


def choices(values, allowed, name):
    if not isinstance(values, list) or len(values) > len(allowed) or any(not isinstance(v, str) or v not in allowed for v in values):
        fail('invalid_input', f'Please check {name}.')
    return sorted(set(values))


def validate_request(body):
    strict_object(body, ('service', 'date', 'time', 'durationMinutes', 'address', 'instructions', 'consent'),
                  ('serviceMinutes','arrangingFor'))
    if body['service'] not in ('cooking', 'cleaning', 'both'):
        fail('invalid_service', 'Choose cooking, cleaning or both.')
    try:
        zone = ZoneInfo(os.getenv('HOME_SERVICE_TIMEZONE', 'America/New_York'))
        local_now = datetime.now(zone)
        day = date.fromisoformat(body['date'])
        start = time.fromisoformat(body['time'])
        if day > local_now.date() + timedelta(days=180):
            raise ValueError()
        if start.tzinfo or start.second or start.microsecond:
            raise ValueError()
        appointment = datetime.combine(day, start, zone)
        # Reject past, nonexistent and ambiguous daylight-saving appointments.
        # No silent conversion can move an older customer's selected visit time.
        if appointment <= local_now or appointment.utcoffset() != appointment.replace(fold=1).utcoffset():
            raise ValueError()
        if appointment.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) != appointment.replace(tzinfo=None):
            raise ValueError()
    except (TypeError, ValueError):
        fail('invalid_schedule', 'Choose a date in the next six months and a local start time.')
    minutes = body['durationMinutes']
    if type(minutes) is not int or not 60 <= minutes <= 480 or minutes % 30:
        fail('invalid_duration', 'Choose one to eight hours in half-hour steps.')
    service_minutes = body.get('serviceMinutes')
    if service_minutes is not None:
        strict_object(service_minutes, ('cooking','cleaning'))
        if any(type(value) is not int or value < 0 or value > 480 or value % 30 for value in service_minutes.values()):
            fail('invalid_duration', 'Use half-hour steps for each service.')
        if (sum(service_minutes.values()) != minutes
            or bool(service_minutes['cooking']) != (body['service'] in ('cooking','both'))
            or bool(service_minutes['cleaning']) != (body['service'] in ('cleaning','both'))):
            fail('scope_mismatch', 'Check the cooking and cleaning time.')
    recipient = body.get('arrangingFor')
    if recipient is not None:
        strict_object(recipient, ('name','permissionConfirmed'))
        if recipient['permissionConfirmed'] is not True:
            fail('recipient_permission_required', 'Confirm that you have permission to arrange this visit and share its details.')
        recipient = {'name': bounded_text(recipient['name'], 'the visit recipient', 120, required=True),
                     'permissionRecordedAt': datetime.now(timezone.utc).isoformat()}
    instructions = body['instructions']
    strict_object(instructions, ('preferences', 'cleaningTasks', 'visitNotes'))
    preferences = choices(instructions['preferences'], PREFERENCES, 'preferences')
    tasks = choices(instructions['cleaningTasks'], CLEANING_TASKS, 'cleaning tasks')
    if tasks and body['service'] == 'cooking':
        fail('invalid_service', 'Cleaning tasks need a cleaning visit.')
    consent = body['consent']
    strict_object(consent, ('version', 'shareWithAssignedHelper'))
    if consent['version'] != CONSENT_VERSION or consent['shareWithAssignedHelper'] is not True:
        fail('consent_required', 'Please confirm sharing these visit details with CookCredit and your assigned helper.')
    return dict(service=body['service'], day=day, start=start, minutes=minutes, time_zone=zone.key,
                service_minutes=service_minutes, recipient=recipient,
                address=bounded_text(body['address'], 'your address', 400, required=True),
                instructions=dict(preferences=preferences, cleaningTasks=tasks,
                    visitNotes=bounded_text(instructions['visitNotes'], 'visit instructions', 1000)))


def sync_identity(session, principal, *, refresh=True):
    # The verified identity supplies these fields, never a client-selected UID or role.
    statement = pg_insert(User.__table__).values(id=principal['uid'], email=principal['email'],
        name=principal.get('name') or principal['email'], roles=['eater'], active_role='eater')
    if refresh:
        session.execute(statement.on_conflict_do_update(index_elements=[User.id],
            set_={'name': statement.excluded.name, 'email': statement.excluded.email}))
    else:
        # Mutations need only an existing actor FK. Updating the indexed email
        # on every command both amplifies writes and can deadlock with another
        # participant's booking FK lock. /me explicitly refreshes profile data.
        session.execute(statement.on_conflict_do_nothing(index_elements=[User.id]))


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def command_reference(key, operation, body):
    if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,128}', key):
        fail('idempotency_key_required', 'A request reference is required. Please retry from the page.')
    try:
        return hashlib.sha256(key.encode()).hexdigest(), fingerprint({'operation': operation, 'body': body})
    except (TypeError, ValueError):
        fail('invalid_json', 'Please check the request fields.')


def replay(session, principal, key, operation, body):
    """Read an already committed result before optional external evidence reads.

    This is an optimization, never the concurrency boundary. command() repeats
    this check under its transaction lock before executing a new mutation.
    """
    digest, request_hash = command_reference(key, operation, body)
    prior = session.get(HomeCommand, (principal['uid'], digest))
    if prior and prior.request_hash != request_hash:
        fail('idempotency_conflict', 'This request reference was already used for a different change.', 409)
    return prior.result if prior else None


def command(session, principal, key, operation, body, execute):
    digest, request_hash = command_reference(key, operation, body)
    sync_identity(session, principal, refresh=False)
    uid = principal['uid']
    # Cross-process transaction lock; no external side effect can escape a rollback.
    session.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))'),
                    {'key': 'home-command:' + uid + ':' + digest})
    prior = session.get(HomeCommand, (uid, digest))
    if prior:
        if prior.request_hash != request_hash:
            fail('idempotency_conflict', 'This request reference was already used for a different change.', 409)
        return prior.result
    result = execute()
    session.add(HomeCommand(actor_id=uid, key_hash=digest, request_hash=request_hash, result=result))
    session.flush()
    return result


def event(session, uid, action, booking_id=None, version=None, **details):
    session.add(HomeEvent(actor_id=uid, action=action, booking_id=booking_id, version=version, details=details))
    session.info['home_dispatch_due'] = datetime.now(timezone.utc)


def create_visit(session, principal, body):
    data = validate_request(body)
    booking_id = uuid.uuid4()
    # No quote exists yet. Zero here is an unpriced legacy field, never a free
    # quote or payment authorization. Future pricing must use an approved quote.
    session.execute(insert(Booking.__table__).values(id=booking_id, eater_id=principal['uid'],
        cook_id=None, status='requested', scheduled_date=data['day'], scheduled_start_time=data['start'],
        estimated_duration=Decimal(data['minutes']) / 60, eater_address=data['address'],
        price_per_hour=0, estimated_total=0))
    session.add(HomeVisit(booking_id=booking_id, service=data['service'], version=0,
        instructions=data['instructions'], time_zone=data['time_zone'], consent_version=CONSENT_VERSION,
        service_minutes=data['service_minutes'], recipient=data['recipient']))
    event(session, principal['uid'], 'visit_requested', booking_id, 0)
    return {'id': str(booking_id), 'version': 0, 'status': 'requested'}


BOOKING_FIELDS = (Booking.id, Booking.eater_id, Booking.cook_id, Booking.status,
    Booking.scheduled_date, Booking.scheduled_start_time, Booking.estimated_duration,
    Booking.eater_address, Booking.created_at, Booking.stripe_payment_intent_id)


def helper_allowed(session, uid, service, *, lock=False):
    permission = session.get(HomeHelperPermission, uid, with_for_update=lock, populate_existing=lock)
    if not permission or not permission.enabled:
        return False
    if service in ('cleaning', 'both') and not permission.cleaning:
        return False
    if service in ('cooking', 'both'):
        query = select(CookProfile.approved).where(CookProfile.user_id == uid)
        if lock:
            query = query.with_for_update()
        return bool(permission.cooking and session.execute(query).scalar())
    return True


def require_free_calendar(session, helper_id, booking, visit):
    """Check an elapsed-time interval while holding the existing helper lock.

    Call only after helper_allowed(..., lock=True). Its permission row already
    serializes assignments for this helper across API workers; no second lock,
    calendar store or process-local availability cache is needed. The query
    never locks another visit, so two operators cannot form a visit-lock cycle.
    """
    start = datetime.combine(booking['scheduled_date'], booking['scheduled_start_time'],
                             ZoneInfo(visit.time_zone)).astimezone(timezone.utc)
    end = start + timedelta(minutes=int(booking['estimated_duration'] * 60))
    if start <= datetime.now(timezone.utc):
        fail('visit_time_passed','The requested start time has passed. Contact CookCredit to arrange a new time.',409)
    # Date bounds keep the indexed candidate set small. Two days on either
    # side cover IANA timezone offsets and Home's maximum eight-hour visit.
    safe_isolation, conflict = session.execute(text("""
        SELECT current_setting('transaction_isolation') = 'read committed', EXISTS (
        SELECT 1 FROM bookings b
        JOIN home_visits v ON v.booking_id = b.id
        WHERE b.cook_id = :helper AND b.id <> :booking
          AND b.status NOT IN ('cancelled', 'completed')
          AND b.scheduled_date BETWEEN :first_day AND :last_day
          AND ((b.scheduled_date + b.scheduled_start_time) AT TIME ZONE v.time_zone) < :ends
          AND (((b.scheduled_date + b.scheduled_start_time) AT TIME ZONE v.time_zone)
               + b.estimated_duration * INTERVAL '1 hour') > :starts
        LIMIT 1)
        """), {'helper': helper_id, 'booking': booking['id'], 'starts': start, 'ends': end,
                'first_day': start.date() - timedelta(days=2), 'last_day': end.date() + timedelta(days=2)}).one()
    if not safe_isolation:
        # The query after a waited helper lock must see the last committed
        # assignment. Reject a database configured to retain an older snapshot.
        fail('calendar_unavailable', 'Scheduling is temporarily unavailable. Please contact CookCredit.', 503)
    if conflict:
        # Never identify the other household, address or visit in this error.
        fail('helper_schedule_conflict',
             'This helper already has a visit at that time. Choose another helper or contact CookCredit.', 409)
    from services.home_availability import require_available
    require_available(session, helper_id, start, end)


def load_visit(session, booking_id, uid, operator, *, lock=False):
    try:
        booking_id = uuid.UUID(str(booking_id))
    except (TypeError, ValueError):
        fail('not_found', 'Visit not found.', 404)
    query = select(*BOOKING_FIELDS, HomeVisit).join(HomeVisit, HomeVisit.booking_id == Booking.id).where(Booking.id == booking_id)
    if not operator:
        query = query.where(or_(Booking.eater_id == uid, Booking.cook_id == uid))
    if lock:
        query = query.with_for_update(of=[Booking, HomeVisit])
    row = session.execute(query).first()
    if not row:
        fail('not_found', 'Visit not found.', 404)
    booking = dict(row._mapping)
    visit = booking.pop('HomeVisit')
    if not operator and booking['eater_id'] != uid and not helper_allowed(session, uid, visit.service):
        fail('not_found', 'Visit not found.', 404)
    return booking, visit


def serialize(booking, visit, *, detail=False):
    result = {'id': str(booking['id']), 'status': booking['status'], 'version': visit.version,
        'service': visit.service, 'date': booking['scheduled_date'].isoformat(),
        'time': booking['scheduled_start_time'].isoformat(),
        'timeZone': visit.time_zone,
        'durationMinutes': int(booking['estimated_duration'] * 60),
        'reviewed': visit.reviewed_at is not None, 'assigned': booking['cook_id'] is not None,
        'helperAccepted': visit.helper_accepted_at is not None, 'issueOpen': visit.issue_open,
        'quoteId': str(visit.quote_id) if visit.quote_id else None,
        'quote': None, 'paymentAvailable': False}
    if detail:
        result.update(address=booking['eater_address'], instructions=visit.instructions,
            serviceMinutes=visit.service_minutes, arrangingFor=visit.recipient,
            consent={'version': visit.consent_version, 'recordedAt': visit.consented_at.isoformat()})
    return result


def transition(session, principal, booking_id, body, operator):
    strict_object(body, ('action', 'version'), ('helperId',))
    if type(body['version']) is not int or body['version'] < 0:
        fail('invalid_version', 'Refresh this visit before making a change.')
    booking, visit = load_visit(session, booking_id, principal['uid'], operator, lock=True)
    if body['version'] != visit.version:
        fail('stale_version', 'This visit changed. Refresh it before continuing.', 409)
    action, status, uid = body['action'], booking['status'], principal['uid']
    # Cancellation freezes the visit, but an existing review hold still needs
    # an authorized resolution. This never reopens the visit or bypasses payment
    # reconciliation; the operator check below applies to every resolution.
    if ((status == 'cancelled' and action != 'resolve_issue')
            or (status == 'completed' and action not in ('report_issue', 'resolve_issue'))):
        fail('visit_closed', 'This visit is already closed.', 409)
    if visit.issue_open and action not in ('cancel', 'resolve_issue'):
        fail('issue_open', 'CookCredit needs to resolve the reported issue first.', 409)
    if 'helperId' in body and action != 'assign':
        fail('invalid_fields', 'Helper selection is only valid when assigning a visit.')
    now = datetime.now(timezone.utc)
    changes = {}
    if action == 'review':
        if not operator:
            fail('forbidden', 'CookCredit review is required.', 403)
        if status != 'requested' or visit.reviewed_at:
            fail('invalid_transition', 'This visit has already been reviewed.', 409)
        visit.reviewed_at, visit.reviewed_by = now, uid
    elif action == 'assign':
        if not operator:
            fail('forbidden', 'Only CookCredit can assign a helper.', 403)
        helper = body.get('helperId')
        if not isinstance(helper, str) or not helper or helper == booking['eater_id']:
            fail('invalid_helper', 'Choose a different, eligible helper.')
        if status != 'requested' or not visit.reviewed_at or visit.helper_accepted_at:
            fail('review_required', 'Review the visit before assigning a helper.', 409)
        if not helper_allowed(session, helper, visit.service, lock=True):
            fail('helper_ineligible', 'This helper is not approved for the requested services.', 409)
        require_free_calendar(session, helper, booking, visit)
        changes['cook_id'] = helper
    elif action == 'accept':
        if booking['cook_id'] != uid or not helper_allowed(session, uid, visit.service, lock=True):
            fail('forbidden', 'Only the assigned helper can accept this visit.', 403)
        if status != 'requested' or not visit.reviewed_at or visit.helper_accepted_at:
            fail('invalid_transition', 'This visit cannot be accepted now.', 409)
        require_free_calendar(session, uid, booking, visit)
        changes['status'], visit.helper_accepted_at = 'accepted', now
    elif action == 'cancel':
        if uid != booking['eater_id'] and not operator:
            fail('forbidden', 'Ask CookCredit to cancel this visit.', 403)
        if status not in ('requested', 'accepted', 'confirmed'):
            fail('cancellation_review_required', 'CookCredit must review this cancellation.', 409)
        changes.update(status='cancelled', cancelled_by='system' if operator else 'eater')
    elif action == 'report_issue':
        # Do not collect sensitive issue text into audit or event payloads.
        visit.issue_open = True
    elif action == 'resolve_issue':
        if not operator:
            fail('forbidden', 'Only CookCredit can resolve a reported issue.', 403)
        if not visit.issue_open:
            fail('invalid_transition', 'There is no open issue.', 409)
        visit.issue_open = False
    elif action in ('start', 'finish', 'confirm'):
        from services.home_payments import service_action
        changes.update(service_action(session, principal, booking, visit, action))
    else:
        fail('unsupported_action', 'This action is not available.')
    visit.version += 1
    if changes:
        session.execute(update(Booking.__table__).where(Booking.id == booking['id']).values(**changes))
        booking.update(changes)
    event(session, uid, action, booking['id'], visit.version,
          **({'helperId': changes['cook_id']} if action == 'assign' else {}))
    session.flush()
    from services.home_payments import on_visit_change
    on_visit_change(session, booking, visit, action)
    return {'id': str(booking['id']), 'version': visit.version, 'status': booking['status']}


def list_visits(session, uid, operator, cursor=None):
    query = select(*BOOKING_FIELDS, HomeVisit).join(HomeVisit, HomeVisit.booking_id == Booking.id)
    if not operator:
        # Helper access requires a live service permission, including cook approval.
        permission = select(HomeHelperPermission.user_id).where(HomeHelperPermission.user_id == uid,
            HomeHelperPermission.enabled.is_(True),
            or_(HomeVisit.service == 'cleaning', and_(HomeHelperPermission.cooking.is_(True),
                select(CookProfile.approved).where(CookProfile.user_id == uid).scalar_subquery().is_(True))),
            or_(HomeVisit.service == 'cooking', HomeHelperPermission.cleaning.is_(True))).exists()
        query = query.where(or_(Booking.eater_id == uid, and_(Booking.cook_id == uid, permission)))
    if cursor:
        try:
            stamp, key = cursor.split('|', 1)
            stamp, key = datetime.fromisoformat(stamp), uuid.UUID(key)
            if stamp.tzinfo is None:
                raise ValueError()
        except (ValueError, TypeError):
            fail('invalid_cursor', 'Please refresh the visit list.')
        query = query.where(or_(Booking.created_at < stamp, and_(Booking.created_at == stamp, Booking.id < key)))
    rows = session.execute(query.order_by(Booking.created_at.desc(), Booking.id.desc()).limit(51)).all()
    visits = []
    for row in rows[:50]:
        booking = dict(row._mapping)
        visits.append(serialize(booking, booking.pop('HomeVisit')))
    last = rows[49]._mapping if len(rows) > 50 else None
    next_cursor = f"{last['created_at'].isoformat()}|{last['id']}" if last else None
    return {'visits': visits, 'nextCursor': next_cursor}


def set_helper_permission(session, principal, helper_id, body):
    strict_object(body, ('enabled', 'cooking', 'cleaning'))
    if any(type(v) is not bool for v in body.values()):
        fail('invalid_permission', 'Permissions must be true or false.')
    if not session.execute(select(User.id).where(User.id == helper_id)).scalar():
        fail('not_found', 'The helper must first sign in to Home.', 404)
    statement = pg_insert(HomeHelperPermission).values(user_id=helper_id, **body)
    session.execute(statement.on_conflict_do_update(index_elements=[HomeHelperPermission.user_id],
        set_={**body, 'updated_at': datetime.now(timezone.utc)}))
    event(session, principal['uid'], 'helper_permission_changed', helperId=helper_id, **body)
    return {'updated': True}
