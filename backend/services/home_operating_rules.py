"""Versioned owner drafts and explicit operating snapshots; no instant bookings."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from sqlalchemy import text, select
from models.home_service import HomeOperatingRules
from services import home_visits as visits

DAYS = ('mon','tue','wed','thu','fri','sat','sun')
STATES = frozenset('AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC'.split())

# Trusted SQL fragments shared by activation, suggestions and locked assignment.
# A helper's server-stamped finish retains its travel margin even after customer
# confirmation. With no travel policy, preserve legacy completed-time release.
PLANNED_START_SQL = '((b.scheduled_date+b.scheduled_start_time) AT TIME ZONE v.time_zone)'
PLANNED_END_SQL = f"({PLANNED_START_SQL}+b.estimated_duration*INTERVAL '1 hour')"
COMMITMENT_START_SQL = f'''CASE WHEN :gap_minutes>0 AND b.completed_at IS NOT NULL
    THEN CASE WHEN b.status='completed' THEN b.completed_at ELSE LEAST({PLANNED_START_SQL},b.completed_at) END
    ELSE {PLANNED_START_SQL} END'''
COMMITMENT_END_SQL = f'''CASE WHEN :gap_minutes>0 AND b.completed_at IS NOT NULL
    THEN CASE WHEN b.status='completed' THEN b.completed_at ELSE GREATEST({PLANNED_END_SQL},b.completed_at) END
    ELSE {PLANNED_END_SQL} END'''
COMMITMENT_CANDIDATES_SQL = '''b.status<>'cancelled' AND (
    (b.status<>'completed' AND b.scheduled_date BETWEEN :first_day AND :last_day)
    OR (:gap_minutes>0 AND b.completed_at BETWEEN :first_time AND :last_time))'''


def defaults():
    # Initial direction only. An empty week stays closed until the owner saves
    # complete settings and explicitly reviews their activation.
    return {'states':['GA'],'timeZone':'America/New_York','noticeHours':24,
            'shortNoticeHours':6,'bufferMinutes':None,'weeklyHours':[]}


def draft(session):
    row = session.get(HomeOperatingRules,1)
    return {'version':row.version if row else 0, 'rules':row.settings if row else defaults(),
            'published':False,'updatedAt':row.updated_at.isoformat() if row else None,
            'activePolicy':snapshot(row) if row else None}


def snapshot(row):
    if not row.active_version:return None
    return {'version':row.active_version,'rules':deepcopy(row.active_settings),
            'activatedAt':row.activated_at.isoformat()}


def active(session,*,lock=False,required=True):
    """Read current operating snapshot, optionally under a transaction share lock.

    Assignment must call this AFTER locking the helper permission and retain
    the transaction. Activation takes policy exclusive and reads commitments
    without helper/booking locks, so the order cannot form a lock cycle.
    """
    query=select(HomeOperatingRules).where(HomeOperatingRules.id==1).execution_options(populate_existing=True)
    if lock:
        require_read_committed(session)
        # Cover the no-row/first-activation race too. Shared advisory readers
        # allow independent helpers to proceed together; owner edits take the
        # same key exclusively and never lock helper or booking rows.
        session.execute(text('SELECT pg_advisory_xact_lock_shared(hashtextextended(:key,0))'),{'key':'home-operating-rules'})
        query=query.with_for_update(read=True)
    row=session.execute(query).scalar_one_or_none()
    value=snapshot(row) if row else None
    if value is None and required:
        visits.fail('operating_rules_required','CookCredit needs to activate its operating rules before scheduling.',409)
    return value


def require_read_committed(session):
    if session.execute(text('SHOW transaction_isolation')).scalar_one()!='read committed':
        visits.fail('calendar_unavailable','Scheduling is temporarily unavailable. Please contact CookCredit.',503)


def window_covers(policy,start,end):
    """Reuse helper coverage's tested midnight/DST elapsed-time primitive.

    Owner windows use quarter-hour minutes. Their conversion to fractional
    hours is exact in binary; no duplicate wall-clock scheduling algorithm.
    """
    if end<=start:return False
    from services.home_availability import covers
    settings=policy['rules']
    return covers({'timeZone':settings['timeZone'],'blockedDates':[],
        'weeklyHours':[{'day':w['day'],'startHour':w['startMinute']/60,'endHour':w['endMinute']/60}
                       for w in settings['weeklyHours']]},start,end)


def require_window(policy,start,end):
    if policy is None:return
    if end<=start or not window_covers(policy,start,end):
        visits.fail('outside_operating_hours','The full visit must fit CookCredit operating hours. Choose another time.',409)


def require_notice(policy,start,reference_time=None,*,manual=False):
    """Use request creation time for later transitions, not acceptance time.

    manual=True is for an explicitly authorized operator path only, never a
    customer-controlled request flag. Pre-activation requests keep their
    original notice terms; this does not bypass operating hours or past starts.
    """
    if policy is None:return
    activated=policy.get('activatedAt')
    if reference_time is not None and activated is not None:
        activated=datetime.fromisoformat(activated) if isinstance(activated,str) else activated
        if reference_time<activated:return
    reference_time=reference_time or datetime.now(timezone.utc)
    hours=policy['rules']['shortNoticeHours' if manual else 'noticeHours']
    if start < reference_time+timedelta(hours=hours):
        visits.fail('booking_notice_required',f'Choose a start at least {hours} hours ahead.',409)


def buffer_minutes(policy):
    return policy['rules']['bufferMinutes'] if policy else 0


def activate(session,principal,body):
    visits.strict_object(body,('version','reviewConfirmed'))
    if type(body['version'])is not int or body['version']<1 or body['reviewConfirmed']is not True:
        visits.fail('operating_rules_review_required','Review the saved operating rules and confirm activation.')
    require_read_committed(session)
    session.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'),{'key':'home-operating-rules'})
    row=session.execute(select(HomeOperatingRules).where(HomeOperatingRules.id==1)
        .with_for_update().execution_options(populate_existing=True)).scalar_one_or_none()
    if row is None or row.version!=body['version']:
        visits.fail('operating_rules_changed','The draft changed. Refresh and review it before activation.',409)
    settings=validate(row.settings)
    if settings['bufferMinutes']is None or not settings['weeklyHours']:
        visits.fail('operating_rules_incomplete','Set operating hours and a travel buffer before activation.')
    if row.active_version==row.version:return {'activated':True,'version':row.version,'published':False,'reviewRequired':True}
    candidate={'version':row.version,'rules':settings};now=datetime.now(timezone.utc)
    # Activation does not silently invalidate work or quote approvals. A policy
    # share lock in assignment makes these READ COMMITTED rows fresh after waits.
    gap=timedelta(minutes=settings['bufferMinutes'])
    rows=session.execute(text(f'''SELECT b.cook_id,b.status,
        {COMMITMENT_START_SQL} AS begins,{COMMITMENT_END_SQL} AS ends
        FROM bookings b JOIN home_visits v ON v.booking_id=b.id
        WHERE b.cook_id IS NOT NULL AND ({COMMITMENT_CANDIDATES_SQL}) LIMIT 1001'''),
        {'gap_minutes':settings['bufferMinutes'],'first_day':now.date()-timedelta(days=2),
         'last_day':now.date()+timedelta(days=367),'first_time':now-gap,
         'last_time':now+timedelta(days=367)}).all()
    if len(rows)>1000:visits.fail('operating_rules_review_required','Contact CookCredit to review existing visits before activation.',409)
    by_helper={}
    for helper,status,begin,end in rows:
        if end<=now-gap:continue
        if status!='completed' and end>now and not window_covers(candidate,begin,end):
            visits.fail('operating_rules_existing_visit','These rules conflict with an assigned visit. Arrange its change before activation.',409)
        by_helper.setdefault(helper,[]).append((begin,end))
    for intervals in by_helper.values():
        intervals.sort()
        latest=None
        for begin,end in intervals:
            if latest is not None and latest+gap>begin and max(latest,end)>now:
                visits.fail('operating_rules_existing_visit','The travel buffer conflicts with assigned visits. Arrange their change before activation.',409)
            latest=max(latest,end) if latest is not None else end
    row.active_version=row.version;row.active_settings=deepcopy(settings)
    row.activated_at=now;row.activated_by=principal['uid']
    visits.event(session,principal['uid'],'operating_rules_activated',policyVersion=row.version,rules=settings)
    from services.home_customers import audit
    audit(session,principal,'operating_rules_activated',row.version)
    return {'activated':True,'version':row.version,'published':False,'reviewRequired':True}


def validate(settings):
    visits.strict_object(settings,('states','timeZone','noticeHours','shortNoticeHours','bufferMinutes','weeklyHours'))
    states = settings['states']
    if not isinstance(states,list) or not 1<=len(states)<=10 or any(not isinstance(s,str) or s not in STATES for s in states):
        visits.fail('invalid_operating_rules','Choose valid US state abbreviations, such as GA.')
    zone = visits.bounded_text(settings['timeZone'],'the service timezone',64,required=True)
    try:ZoneInfo(zone)
    except (ZoneInfoNotFoundError,ValueError):visits.fail('invalid_operating_rules','Choose a valid service timezone.')
    notice,short = settings['noticeHours'],settings['shortNoticeHours']
    if type(notice)is not int or type(short)is not int or not 6<=short<=notice<=168:
        visits.fail('invalid_operating_rules','Use six hours to seven days of notice; short notice cannot exceed the default.')
    buffer = settings['bufferMinutes']
    if buffer is not None and (type(buffer)is not int or not 0<=buffer<=180 or buffer%15):
        visits.fail('invalid_operating_rules','Use a travel buffer from zero to 180 minutes in 15-minute steps.')
    hours = settings['weeklyHours']
    if not isinstance(hours,list) or len(hours)>7:
        visits.fail('invalid_operating_rules','Set at most one operating window per weekday.')
    seen=set();clean=[]
    for window in hours:
        visits.strict_object(window,('day','startMinute','endMinute'))
        day,start,end=window['day'],window['startMinute'],window['endMinute']
        if (not isinstance(day,str) or day not in DAYS or day in seen
            or type(start)is not int or type(end)is not int or not 0<=start<end<=1440 or start%15 or end%15):
            visits.fail('invalid_operating_rules','Check each weekday and its opening and closing times.')
        seen.add(day);clean.append({'day':day,'startMinute':start,'endMinute':end})
    clean.sort(key=lambda value:DAYS.index(value['day']))
    return {'states':sorted(set(states)),'timeZone':zone,'noticeHours':notice,'shortNoticeHours':short,
            'bufferMinutes':buffer,'weeklyHours':clean}


def save(session,principal,body):
    visits.strict_object(body,('version','rules'))
    if type(body['version'])is not int or body['version']<0:
        visits.fail('invalid_version','Refresh the operating rules before saving.')
    settings=validate(body['rules'])
    # Serialize first insert as well as later edits across two owner tabs.
    session.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'),{'key':'home-operating-rules'})
    row=session.get(HomeOperatingRules,1,populate_existing=True)
    current=row.version if row else 0
    if body['version']!=current:
        visits.fail('operating_rules_changed','Another edit changed these rules. Refresh before saving.',409)
    if row and row.settings==settings:return {'saved':True,'version':current,'published':False}
    if row:
        row.version+=1;row.settings=settings;row.updated_by=principal['uid'];row.updated_at=datetime.now(timezone.utc)
    else:
        row=HomeOperatingRules(id=1,version=1,settings=settings,updated_by=principal['uid'])
        session.add(row)
    # These are business settings, never household details. Preserve the exact
    # revision in the existing immutable event stream, with a pointer in access audit.
    visits.event(session,principal['uid'],'operating_rules_draft_saved',policyVersion=row.version,rules=settings)
    from services.home_customers import audit
    audit(session,principal,'operating_rules_draft_saved',row.version)
    return {'saved':True,'version':row.version,'published':False}
