"""Home quotes: immutable offers, integer money and explicit approvals.

Reuse Home's identity/authorization, booking locks, audit and idempotent commands.
No Stripe requests, bank effects, automatic tax decisions or seeded live prices.
"""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo
from sqlalchemy import select, update
from models import Booking
from models.home_service import (HomeRateCard, HomePricingHead, HomeQuote,
    HomeQuoteHelperAcceptance, HomeQuoteApproval, HomeMaterialReconciliation)
from services import home_visits as visits


def now():
    return datetime.now(timezone.utc)


def identifier(value):
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        visits.fail('invalid_reference', 'Please refresh this page and try again.')


def integer(value, name, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        visits.fail('invalid_amount', f'Please check {name}.')
    return value


def rounded_ratio(amount, numerator, denominator):
    """Round nonnegative integer products half up; never use binary floats."""
    return (amount * numerator + denominator // 2) // denominator


def validate_rates(body):
    visits.strict_object(body, ('previousId', 'currency', 'rates', 'customerFeeBps',
        'helperCommissionBps', 'materialsCapCents', 'quoteValidMinutes'))
    if body['currency'] != 'usd':
        visits.fail('unsupported_currency', 'Home pricing currently supports USD.')
    visits.strict_object(body['rates'], ('cookingHourlyCents', 'cleaningHourlyCents'))
    rates = {name: integer(value, 'the hourly rate', 100, 100000) for name, value in body['rates'].items()}
    settings = {'currency': 'usd', 'rates': rates,
        'customerFeeBps': integer(body['customerFeeBps'], 'the customer fee', 0, 10000),
        'helperCommissionBps': integer(body['helperCommissionBps'], 'the helper commission', 0, 10000),
        'materialsCapCents': integer(body['materialsCapCents'], 'the materials limit', 0, 1000000),
        'quoteValidMinutes': integer(body['quoteValidMinutes'], 'the quote validity period', 30, 10080)}
    previous = None if body['previousId'] is None else identifier(body['previousId'])
    return settings, previous


def rate_dict(card):
    return {'id': str(card.id), 'previousId': str(card.previous_id) if card.previous_id else None,
            **card.settings, 'createdAt': card.created_at.isoformat()}


def pricing(session):
    head = session.get(HomePricingHead, 1)
    cards = session.execute(select(HomeRateCard).order_by(HomeRateCard.created_at.desc(), HomeRateCard.id.desc()).limit(50)).scalars().all()
    return {'activeId': str(head.rate_card_id) if head and head.rate_card_id else None,
            'versions': [rate_dict(card) for card in cards], 'paymentsAvailable': False}


def save_rates(session, principal, body):
    settings, previous = validate_rates(body)
    head = session.get(HomePricingHead, 1, with_for_update=True)
    if head.rate_card_id != previous:
        visits.fail('pricing_changed', 'The active pricing changed. Refresh before saving.', 409)
    card = HomeRateCard(previous_id=previous, settings=settings, created_by=principal['uid'])
    session.add(card)
    session.flush()
    visits.event(session, principal['uid'], 'rate_card_created', rateCardId=str(card.id))
    return {'rateCardId': str(card.id), 'active': False}


def activate_rates(session, principal, rate_card_id, body):
    visits.strict_object(body, ())
    card = session.get(HomeRateCard, identifier(rate_card_id))
    if not card:
        visits.fail('not_found', 'Pricing version not found.', 404)
    head = session.get(HomePricingHead, 1, with_for_update=True)
    if head.rate_card_id == card.id:
        return {'rateCardId': str(card.id), 'active': True}
    if head.rate_card_id != card.previous_id:
        visits.fail('pricing_changed', 'A different pricing version is active. Save a new version.', 409)
    head.rate_card_id = card.id
    visits.event(session, principal['uid'], 'rate_card_activated', rateCardId=str(card.id))
    return {'rateCardId': str(card.id), 'active': True}


def load_locked(session, principal, booking_id, body, operator):
    integer(body['version'], 'the visit version', 0, 2147483647)
    booking, visit = visits.load_visit(session, booking_id, principal['uid'], operator, lock=True)
    if visit.version != body['version']:
        visits.fail('stale_version', 'This visit changed. Refresh it before continuing.', 409)
    return booking, visit


def offer_ready(session, booking, visit):
    if booking['status'] != 'accepted' or not visit.helper_accepted_at or not visit.reviewed_at or visit.issue_open:
        visits.fail('quote_not_ready', 'Review the visit and obtain helper acceptance before quoting.', 409)
    if not visits.helper_allowed(session, booking['cook_id'], visit.service, lock=True):
        visits.fail('helper_ineligible', 'This helper is no longer approved for the visit.', 409)
    if booking['stripe_payment_intent_id']:
        # Stage 4 must provide an explicit void/refund/requote lifecycle. Never
        # silently replace the price after a payment attempt has been created.
        visits.fail('payment_in_progress', 'Review the existing payment before changing this quote.', 409)


def scope_digest(booking, visit):
    return visits.fingerprint({'bookingId': str(booking['id']), 'helperId': booking['cook_id'],
        'service': visit.service, 'date': booking['scheduled_date'].isoformat(),
        'time': booking['scheduled_start_time'].isoformat(), 'timeZone': visit.time_zone,
        'durationMinutes': int(booking['estimated_duration'] * 60), 'address': booking['eater_address'],
        'instructions': visit.instructions, 'consentVersion': visit.consent_version})


def review_tax(body):
    visits.strict_object(body, ('amountCents', 'reviewConfirmed', 'reviewReference'))
    if body['reviewConfirmed'] is not True:
        visits.fail('tax_review_required', 'Confirm the tax review before issuing this quote.')
    amount = integer(body['amountCents'], 'the reviewed tax amount', 0, 1000000)
    reference = visits.bounded_text(body['reviewReference'], 'the tax review reference', 120, required=True)
    return {'amountCents': amount, 'reviewReference': reference}


def calculate(settings, service, duration, cooking_minutes, cleaning_minutes, materials, tax):
    """Create the customer cap and estimated helper allocation from trusted rates."""
    for value in (cooking_minutes, cleaning_minutes):
        integer(value, 'the service minutes', 0, 480)
        if value % 30:
            visits.fail('invalid_duration', 'Use half-hour steps for cooking and cleaning.')
    if cooking_minutes + cleaning_minutes != duration or (
        bool(cooking_minutes) != (service in ('cooking', 'both')) or
        bool(cleaning_minutes) != (service in ('cleaning', 'both'))):
        visits.fail('scope_mismatch', 'The quoted work must match the requested service and duration.')
    if not isinstance(materials, list) or len(materials) > 20:
        visits.fail('invalid_materials', 'Use at most twenty itemized materials allowances.')
    material_lines = []
    for item in materials:
        visits.strict_object(item, ('category', 'label', 'capCents'))
        # Cooking can need non-food supplies too (containers, labels or foil).
        # Ingredients still require a cooking scope; every allowance is approved.
        if item['category'] not in ('ingredients', 'supplies') or (
            item['category'] == 'ingredients' and service == 'cleaning'):
            visits.fail('scope_mismatch', 'Materials must match the requested services.')
        material_lines.append({'lineId': str(uuid.uuid4()), 'category': item['category'],
            'label': visits.bounded_text(item['label'], 'the material label', 120, required=True),
            'capCents': integer(item['capCents'], 'the material allowance', 1, settings['materialsCapCents'])})
    material_cap = sum(item['capCents'] for item in material_lines)
    if material_cap > settings['materialsCapCents']:
        visits.fail('materials_limit', 'The materials allowance exceeds the active pricing limit.')
    labor = []
    for kind, minutes in (('cooking', cooking_minutes), ('cleaning', cleaning_minutes)):
        if minutes:
            rate = settings['rates'][kind + 'HourlyCents']
            labor.append({'service': kind, 'minutes': minutes, 'rateCentsPerHour': rate,
                          'amountCents': rounded_ratio(rate, minutes, 60)})
    labor_cents = sum(line['amountCents'] for line in labor)
    fee = rounded_ratio(labor_cents, settings['customerFeeBps'], 10000)
    commission = rounded_ratio(labor_cents, settings['helperCommissionBps'], 10000)
    return {'currency': settings['currency'], 'labor': labor, 'materials': material_lines,
        'laborCents': labor_cents, 'materialsCapCents': material_cap, 'serviceFeeCents': fee,
        'taxCapCents': tax['amountCents'], 'maximumTotalCents': labor_cents + material_cap + fee + tax['amountCents'],
        'helperCommissionCents': commission, 'helperLaborNetCents': labor_cents - commission,
        'platformRevenueCents': fee + commission}


def issue_quote(session, principal, booking_id, body, operator):
    visits.strict_object(body, ('version', 'rateCardId', 'cookingMinutes', 'cleaningMinutes', 'materials', 'tax'))
    if not operator:
        visits.fail('forbidden', 'Only CookCredit can issue a quote.', 403)
    booking, visit = load_locked(session, principal, booking_id, body, operator)
    offer_ready(session, booking, visit)
    # Shared lock lets different bookings quote concurrently, while activation
    # serializes against issuance. An old published card is not silently reused.
    head = session.get(HomePricingHead, 1, with_for_update={'read': True})
    card_id = identifier(body['rateCardId'])
    if head.rate_card_id is None or head.rate_card_id != card_id:
        visits.fail('pricing_changed', 'Refresh the active pricing before issuing a quote.', 409)
    card = session.get(HomeRateCard, card_id)
    tax = review_tax(body['tax'])
    if 'customer_supplies' in visit.instructions['preferences'] and body['materials']:
        visits.fail('customer_supplies', 'This customer chose to supply the materials. Resolve that scope before quoting purchases.')
    snapshot = calculate(card.settings, visit.service, int(booking['estimated_duration'] * 60),
        body['cookingMinutes'], body['cleaningMinutes'], body['materials'], tax)
    created = now()
    appointment = datetime.combine(booking['scheduled_date'], booking['scheduled_start_time'], ZoneInfo(visit.time_zone)).astimezone(timezone.utc)
    expires = min(created + timedelta(minutes=card.settings['quoteValidMinutes']), appointment)
    if expires <= created:
        visits.fail('visit_in_past', 'Choose a future visit before issuing a quote.', 409)
    quote_id = uuid.uuid4()
    visit.version += 1
    snapshot.update(quoteId=str(quote_id), rateCardId=str(card.id), scopeDigest=scope_digest(booking, visit),
        helperId=booking['cook_id'], issuedVersion=visit.version, createdAt=created.isoformat(), expiresAt=expires.isoformat(),
        taxReview=tax)
    quote = HomeQuote(id=quote_id, booking_id=booking['id'], rate_card_id=card.id, helper_id=booking['cook_id'],
        issued_version=visit.version, snapshot=snapshot, digest=visits.fingerprint(snapshot),
        created_by=principal['uid'], created_at=created, expires_at=expires)
    session.add(quote)
    session.flush()  # The current-pointer FK must reference an already-persisted offer.
    visit.quote_id = quote_id
    # Legacy estimates mirror the immutable offer only; they never authorize payment.
    session.execute(update(Booking.__table__).where(Booking.id == booking['id']).values(
        estimated_total=Decimal(snapshot['maximumTotalCents']) / 100))
    visits.event(session, principal['uid'], 'quote_issued', booking['id'], visit.version, quoteId=str(quote_id))
    return {'id': str(booking['id']), 'quoteId': str(quote_id), 'version': visit.version, 'status': booking['status']}


def current_quote(session, booking, visit, quote_id):
    key = identifier(quote_id)
    if visit.quote_id != key:
        visits.fail('quote_changed', 'This quote was replaced. Refresh to see the current offer.', 409)
    quote = session.get(HomeQuote, key)
    if quote.booking_id != booking['id'] or quote.helper_id != booking['cook_id'] or quote.snapshot['scopeDigest'] != scope_digest(booking, visit):
        visits.fail('scope_changed', 'The visit changed. CookCredit must issue a new quote.', 409)
    return quote


def accept_quote(session, principal, booking_id, quote_id, body, operator, *, helper=False):
    visits.strict_object(body, ('version', 'digest'))
    booking, visit = load_locked(session, principal, booking_id, body, operator)
    actor = booking['cook_id'] if helper else booking['eater_id']
    if principal['uid'] != actor:
        visits.fail('forbidden', 'Only the assigned helper can accept this quote.' if helper else 'Only the customer can approve this quote.', 403)
    offer_ready(session, booking, visit)
    quote = current_quote(session, booking, visit, quote_id)
    if now() >= quote.expires_at:
        visits.fail('quote_expired', 'This quote expired. Ask CookCredit for a new offer.', 409)
    if body['digest'] != quote.digest:
        visits.fail('quote_changed', 'Review the current quote before approving it.', 409)
    model = HomeQuoteHelperAcceptance if helper else HomeQuoteApproval
    if session.get(model, quote.id):
        visits.fail('already_approved', 'This quote has already been accepted.', 409)
    if not helper and not session.get(HomeQuoteHelperAcceptance, quote.id):
        visits.fail('helper_quote_pending', 'Your helper must accept the itemized work and earnings first.', 409)
    fields = {'helper_id' if helper else 'customer_id': principal['uid']}
    session.add(model(quote_id=quote.id, digest=quote.digest, **fields))
    visit.version += 1
    visits.event(session, principal['uid'], 'helper_quote_accepted' if helper else 'quote_approved',
                 booking['id'], visit.version, quoteId=str(quote.id))
    session.flush()
    return {'id': str(booking['id']), 'quoteId': str(quote.id), 'version': visit.version,
            'status': booking['status'], 'paymentAvailable': False}


def quote_for_visit(session, booking, visit, uid, operator):
    if not visit.quote_id:
        return None
    row = session.execute(select(HomeQuote, HomeQuoteHelperAcceptance, HomeQuoteApproval, HomeMaterialReconciliation)
        .outerjoin(HomeQuoteHelperAcceptance, HomeQuoteHelperAcceptance.quote_id == HomeQuote.id)
        .outerjoin(HomeQuoteApproval, HomeQuoteApproval.quote_id == HomeQuote.id)
        .outerjoin(HomeMaterialReconciliation, HomeMaterialReconciliation.quote_id == HomeQuote.id)
        .where(HomeQuote.id == visit.quote_id)).one()
    quote, helper_acceptance, approval, reconciliation = row
    s = quote.snapshot
    result = {key: s[key] for key in ('currency', 'labor', 'materials', 'laborCents', 'materialsCapCents',
        'serviceFeeCents', 'taxCapCents', 'maximumTotalCents')}
    result.update(id=str(quote.id), rateCardId=str(quote.rate_card_id), digest=quote.digest,
        expiresAt=quote.expires_at.isoformat(), expired=now() >= quote.expires_at,
        helperAcceptedQuote=helper_acceptance is not None, approved=approval is not None,
        approvedAt=approval.created_at.isoformat() if approval else None,
        paymentsAvailable=False)
    if operator or uid == booking['cook_id']:
        result['helperEarnings'] = {'laborNetCents': s['helperLaborNetCents'], 'commissionCents': s['helperCommissionCents'],
            'materialsMaximumCents': s['materialsCapCents'], 'maximumPayCents': s['helperLaborNetCents'] + s['materialsCapCents']}
    if reconciliation:
        result['reconciliation'] = {key: reconciliation.snapshot[key] for key in (
            'materialsActualCents', 'taxActualCents', 'customerFinalCents', 'unusedAllowanceCents')}
        if operator or uid == booking['cook_id']:
            result['reconciliation']['helperActualPayCents'] = reconciliation.snapshot['helperActualPayCents']
    return result


def reconcile_materials(session, principal, booking_id, body, operator):
    visits.strict_object(body, ('version', 'quoteId', 'lines', 'tax', 'receiptsReviewed'))
    if not operator:
        visits.fail('forbidden', 'Only CookCredit can reconcile material receipts.', 403)
    booking, visit = load_locked(session, principal, booking_id, body, operator)
    if booking['status'] not in ('pending_confirmation', 'completed') or visit.issue_open:
        visits.fail('receipts_not_ready', 'Review receipts after the work is finished and resolve open issues first.', 409)
    quote = current_quote(session, booking, visit, body['quoteId'])
    if not session.get(HomeQuoteApproval, quote.id):
        visits.fail('approval_required', 'The customer must have approved this quote.', 409)
    if session.get(HomeMaterialReconciliation, quote.id):
        visits.fail('already_reconciled', 'These receipts are already reconciled. Contact CookCredit to review a correction.', 409)
    if body['receiptsReviewed'] is not True:
        visits.fail('receipt_review_required', 'Confirm that the receipts were reviewed.')
    quoted = {line['lineId']: line for line in quote.snapshot['materials']}
    lines = body['lines']
    if not isinstance(lines, list) or len(lines) != len(quoted):
        visits.fail('invalid_receipts', 'Review every quoted materials allowance once.')
    recorded, seen = [], set()
    for line in lines:
        visits.strict_object(line, ('lineId', 'actualCents', 'receiptReference'))
        key = str(identifier(line['lineId']))
        if key not in quoted or key in seen:
            visits.fail('invalid_receipts', 'Review every quoted materials allowance once.')
        seen.add(key)
        actual = integer(line['actualCents'], 'the actual material cost', 0, quoted[key]['capCents'])
        reference = str(identifier(line['receiptReference'])) if actual else None
        if not actual and line['receiptReference'] is not None:
            reference = str(identifier(line['receiptReference']))
        recorded.append({'lineId': key, 'actualCents': actual, 'receiptReference': reference})
    tax = review_tax(body['tax'])
    if tax['amountCents'] > quote.snapshot['taxCapCents']:
        visits.fail('tax_limit', 'The final tax cannot exceed the approved quote allowance.')
    s = quote.snapshot
    materials = sum(line['actualCents'] for line in recorded)
    total = s['laborCents'] + s['serviceFeeCents'] + materials + tax['amountCents']
    result = {'lines': recorded, 'taxReview': tax, 'materialsActualCents': materials,
        'taxActualCents': tax['amountCents'], 'customerFinalCents': total,
        'unusedAllowanceCents': s['maximumTotalCents'] - total,
        'helperActualPayCents': s['helperLaborNetCents'] + materials}
    session.add(HomeMaterialReconciliation(quote_id=quote.id, booking_id=booking['id'],
        reviewed_by=principal['uid'], snapshot=result))
    visit.version += 1
    visits.event(session, principal['uid'], 'materials_reconciled', booking['id'], visit.version, quoteId=str(quote.id))
    session.flush()
    return {'id': str(booking['id']), 'quoteId': str(quote.id), 'version': visit.version,
            'status': booking['status'], 'paymentAvailable': False}
