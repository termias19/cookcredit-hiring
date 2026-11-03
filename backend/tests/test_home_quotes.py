"""Authoritative Home quotes and pricing; no payments or cloud requests."""
import uuid
import io
from PIL import Image
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
import threading

import pytest
from sqlalchemy import select, update, text
from sqlalchemy.exc import IntegrityError
from models import Booking, User
from models.home_service import (HomeVisit, HomeRateCard, HomeQuote, HomeQuoteApproval,
    HomeQuoteHelperAcceptance, HomeMaterialReconciliation, HomeCommand)
from services import database, home_quotes as quotes, home_visits as visits
from tests.test_home_visits import home_db, app, headers, payload, create, change, seed_helper


def rates(previous=None):
    # Synthetic prices; never seeded or published by application startup.
    return {'previousId': previous, 'currency': 'usd',
        'rates': {'cookingHourlyCents': 4501, 'cleaningHourlyCents': 3999},
        'customerFeeBps': 1000, 'helperCommissionBps': 1500,
        'materialsCapCents': 10000, 'quoteValidMinutes': 1440}


def post(client, path, body, uid='owner', key=None):
    return client.post('/api/home' + path, json=body, headers=headers(uid, key or uuid.uuid4().hex))


def activate(client, body=None):
    created = post(client, '/pricing', body or rates())
    assert created.status_code == 201, created.json
    card = created.json['rateCardId']
    assert post(client, f'/pricing/{card}/activate', {}).status_code == 200
    return card


def prepared(client, request=None):
    row = create(client, request).json
    assert seed_helper(client).status_code == 200
    row = change(client, row, 'review').json
    row = change(client, row, 'assign', helperId='helper').json
    return change(client, row, 'accept', uid='helper').json


def offer_body(row, card, *, materials=True):
    return {'version': row['version'], 'rateCardId': card, 'cookingMinutes': 90, 'cleaningMinutes': 60,
        'materials': [{'category': 'ingredients', 'label': 'Example groceries', 'capCents': 2500},
                      {'category': 'supplies', 'label': 'Example cleaning supplies', 'capCents': 500}] if materials else [],
        'tax': {'amountCents': 777, 'reviewConfirmed': True, 'reviewReference': 'synthetic-tax-review'}}


def offer(client, row, card, body=None, key=None):
    result = post(client, f"/visits/{row['id']}/quotes", body or offer_body(row, card), key=key)
    assert result.status_code == 201, result.json
    return result.json


def detail(client, row, uid='customer'):
    response = client.get('/api/home/visits/' + row['id'], headers=headers(uid))
    assert response.status_code == 200, response.json
    return response.json


def approve(client, row, uid='customer', *, key=None, digest=None):
    quote = detail(client, row, uid)['quote']
    decision = 'accept' if uid == 'helper' else 'approve'
    return post(client, f"/visits/{row['id']}/quotes/{quote['id']}/{decision}",
        {'version': row['version'], 'digest': digest or quote['digest']}, uid, key)


def fully_approved(client, *, no_materials=False):
    row = prepared(client)
    card = activate(client)
    row = offer(client, row, card, offer_body(row, card, materials=not no_materials))
    row = approve(client, row, uid='helper').json
    result = approve(client, row)
    assert result.status_code == 200, result.json
    return result.json, card


def test_integer_money_rounding_and_conservation():
    settings, _ = quotes.validate_rates(rates())
    for cooking in (30, 60, 90, 180):
        for cleaning in (30, 60, 90):
            result = quotes.calculate(settings, 'both', cooking + cleaning, cooking, cleaning, [], {'amountCents': 123})
            assert result['labor'][0]['amountCents'] == int((Decimal(4501) * cooking / 60).quantize(Decimal(1), rounding='ROUND_HALF_UP'))
            assert result['helperLaborNetCents'] + result['platformRevenueCents'] + 123 == result['maximumTotalCents']
            assert all(type(result[key]) is int for key in ('laborCents', 'serviceFeeCents', 'maximumTotalCents'))


def test_cooking_can_include_storage_supplies_but_cleaning_cannot_add_food():
    settings, _ = quotes.validate_rates(rates())
    line = {'category': 'supplies', 'label': 'Food storage containers', 'capCents': 500}
    result = quotes.calculate(settings, 'cooking', 90, 90, 0, [line], {'amountCents': 0})
    assert result['materialsCapCents'] == 500
    line['category'] = 'ingredients'
    with pytest.raises(visits.HomeError, match='Materials must match'):
        quotes.calculate(settings, 'cleaning', 90, 0, 90, [line], {'amountCents': 0})


def test_owner_only_versioned_rates_and_stale_activation(app):
    client = app.test_client()
    assert client.get('/api/home/pricing', headers=headers('customer')).status_code == 403
    assert post(client, '/pricing', rates(), 'operator').status_code == 403
    assert client.get('/api/home/pricing', headers=headers('owner')).json['activeId'] is None
    first = post(client, '/pricing', rates()).json['rateCardId']
    second = post(client, '/pricing', rates()).json['rateCardId']
    assert post(client, f'/pricing/{first}/activate', {}, 'operator').status_code == 403
    assert post(client, f'/pricing/{first}/activate', {}).status_code == 200
    assert post(client, f'/pricing/{second}/activate', {}).json['code'] == 'pricing_changed'
    assert post(client, '/pricing', rates()).json['code'] == 'pricing_changed'
    replacement = rates(first)
    replacement['rates']['cleaningHourlyCents'] = 4200
    third = activate(client, replacement)
    result = client.get('/api/home/pricing', headers=headers('operator')).json
    assert result['activeId'] == third and len(result['versions']) == 3
    with database.db_session() as session:
        assert session.get(HomeRateCard, uuid.UUID(first)).settings['rates']['cleaningHourlyCents'] == 3999


def test_accepted_scope_quote_helper_earnings_customer_approval_and_audit(app):
    client = app.test_client()
    row = prepared(client)
    card = activate(client)
    assert post(client, f"/visits/{row['id']}/quotes", offer_body(row, card), 'customer').status_code == 403
    row = offer(client, row, card)
    customer = detail(client, row)
    quote = customer['quote']
    assert quote['laborCents'] == 10751 and quote['serviceFeeCents'] == 1075
    assert quote['maximumTotalCents'] == 15603 and quote['materialsCapCents'] == 3000
    assert quote['taxCapCents'] == 777 and not quote['paymentsAvailable']
    assert 'helperEarnings' not in quote and 'taxReview' not in quote
    assert approve(client, row).json['code'] == 'helper_quote_pending'
    assert approve(client, row, uid='owner').status_code == 403
    helper = detail(client, row, 'helper')['quote']['helperEarnings']
    assert helper['commissionCents'] == 1613 and helper['maximumPayCents'] == 12138
    accepted = approve(client, row, uid='helper')
    assert accepted.status_code == 200
    row = accepted.json
    assert approve(client, row, digest='0' * 64).json['code'] == 'quote_changed'
    approved = approve(client, row)
    assert approved.status_code == 200 and not approved.json['paymentAvailable']
    assert detail(client, approved.json)['quote']['approved'] is True
    events = client.get('/api/home/visits/' + row['id'] + '/activity', headers=headers('owner')).json['events']
    assert [e['action'] for e in events][-3:] == ['quote_issued', 'helper_quote_accepted', 'quote_approved']
    assert 'Example groceries' not in str(events) and 'synthetic-tax-review' not in str(events)


def test_rate_change_does_not_mutate_approved_quote_requote_requires_new_approvals(app):
    client = app.test_client()
    row, card = fully_approved(client)
    old = detail(client, row)['quote']
    replacement = rates(card)
    replacement['rates']['cookingHourlyCents'] = 5000
    new_card = activate(client, replacement)
    assert detail(client, row)['quote']['digest'] == old['digest']
    assert detail(client, row)['quote']['maximumTotalCents'] == old['maximumTotalCents']
    assert post(client, f"/visits/{row['id']}/quotes", offer_body(row, card)).json['code'] == 'pricing_changed'
    row = offer(client, row, new_card)
    new = detail(client, row)['quote']
    assert not new['approved'] and not new['helperAcceptedQuote'] and new['digest'] != old['digest']
    result = post(client, f"/visits/{row['id']}/quotes/{old['id']}/approve",
        {'version': row['version'], 'digest': old['digest']}, 'customer')
    assert result.json['code'] == 'quote_changed'
    historical = client.get(f"/api/home/visits/{row['id']}/quotes/{old['id']}", headers=headers()).json['quote']
    assert historical['approved'] and not historical['current'] and historical['digest'] == old['digest']
    assert historical['maximumTotalCents'] == old['maximumTotalCents']
    assert client.get(f"/api/home/visits/{row['id']}/quotes/{old['id']}", headers=headers('stranger')).status_code == 404
    with database.db_session() as session:
        assert session.query(HomeQuote).count() == 2 and session.query(HomeQuoteApproval).count() == 1


@pytest.mark.parametrize('mutation', ['missing_tax', 'unreviewed_tax', 'negative_tax', 'float_rate',
    'scope', 'fee_override', 'excess_materials', 'wrong_material_kind', 'boolean_minutes'])
def test_rejects_unreviewed_or_forged_quote_inputs(app, mutation):
    client = app.test_client()
    row = prepared(client)
    if mutation == 'float_rate':
        body = rates()
        body['rates']['cookingHourlyCents'] = 45.01
        assert post(client, '/pricing', body).status_code == 400
        return
    card = activate(client)
    body = offer_body(row, card)
    if mutation == 'missing_tax': del body['tax']
    elif mutation == 'unreviewed_tax': body['tax']['reviewConfirmed'] = False
    elif mutation == 'negative_tax': body['tax']['amountCents'] = -1
    elif mutation == 'scope': body['cookingMinutes'] = 120
    elif mutation == 'fee_override': body['serviceFeeCents'] = 0
    elif mutation == 'excess_materials': body['materials'][0]['capCents'] = 10001
    elif mutation == 'wrong_material_kind': body['materials'][0]['category'] = 'other'
    elif mutation == 'boolean_minutes': body['cookingMinutes'] = True
    assert post(client, f"/visits/{row['id']}/quotes", body).status_code == 400


def test_customer_supplies_choice_is_not_overridden(app):
    client = app.test_client()
    request = payload()
    request['instructions']['preferences'].append('customer_supplies')
    row = prepared(client, request)
    card = activate(client)
    assert post(client, f"/visits/{row['id']}/quotes", offer_body(row, card)).json['code'] == 'customer_supplies'
    row = offer(client, row, card, offer_body(row, card, materials=False))
    assert detail(client, row)['quote']['materialsCapCents'] == 0


def test_expiry_scope_integrity_and_revoked_helper(app, monkeypatch):
    client = app.test_client()
    row = prepared(client)
    card = activate(client)
    row = offer(client, row, card)
    with database.db_session() as session:
        quote = session.get(HomeQuote, uuid.UUID(row['quoteId']))
        expiry = quote.expires_at
    monkeypatch.setattr(quotes, 'now', lambda: expiry)
    assert approve(client, row, uid='helper').json['code'] == 'quote_expired'
    monkeypatch.setattr(quotes, 'now', lambda: expiry - timedelta(minutes=10))
    with database.db_session() as session:
        session.execute(update(Booking).where(Booking.id == uuid.UUID(row['id'])).values(eater_address='changed after offer'))
    assert approve(client, row, uid='helper').json['code'] == 'scope_changed'
    with database.db_session() as session:
        session.execute(update(Booking).where(Booking.id == uuid.UUID(row['id'])).values(eater_address=payload()['address']))
    client.put('/api/home/helpers/helper/permission', headers=headers('owner', uuid.uuid4().hex),
        json={'enabled': False, 'cooking': True, 'cleaning': True})
    assert approve(client, row).json['code'] == 'helper_ineligible'


def test_expiry_never_runs_past_appointment_and_payment_reference_blocks_requote(app):
    client = app.test_client()
    row = prepared(client)
    settings = rates()
    settings['quoteValidMinutes'] = 10080
    card = activate(client, settings)
    row = offer(client, row, card)
    with database.db_session() as session:
        booking, visit = visits.load_visit(session, row['id'], 'owner', True)
        quote = session.get(HomeQuote, uuid.UUID(row['quoteId']))
        assert quote.expires_at.date() == booking['scheduled_date']
        session.execute(update(Booking).where(Booking.id == uuid.UUID(row['id'])).values(stripe_payment_intent_id='synthetic-not-a-payment'))
    assert post(client, f"/visits/{row['id']}/quotes", offer_body(row, card)).json['code'] == 'payment_in_progress'


def test_concurrent_duplicate_quote_and_customer_approval_are_deduplicated(app):
    client = app.test_client()
    row = prepared(client)
    card, key = activate(client), uuid.uuid4().hex
    body = offer_body(row, card)
    def issue(_):
        with app.test_client() as worker:
            response = post(worker, f"/visits/{row['id']}/quotes", body, key=key)
            return response.status_code, response.json
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(issue, range(4)))
    assert {r[0] for r in results} == {201} and len({r[1]['quoteId'] for r in results}) == 1
    row = approve(client, results[0][1], uid='helper').json
    key = uuid.uuid4().hex
    def accept(_):
        with app.test_client() as worker:
            response = approve(worker, row, key=key)
            return response.status_code, response.json
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(accept, range(4)))
    assert {r[0] for r in results} == {200} and len({r[1]['version'] for r in results}) == 1
    with database.db_session() as session:
        assert session.query(HomeQuote).count() == session.query(HomeQuoteApproval).count() == 1


def test_quote_failure_rolls_back_offer_pointer_version_and_estimate(app, monkeypatch):
    client = app.test_client()
    row = prepared(client)
    card = activate(client)
    original = visits.event
    def broken(session, uid, action, *args, **kwargs):
        if action == 'quote_issued': raise RuntimeError('synthetic failure')
        return original(session, uid, action, *args, **kwargs)
    monkeypatch.setattr(visits, 'event', broken)
    result = post(client, f"/visits/{row['id']}/quotes", offer_body(row, card))
    assert result.status_code == 503
    with database.db_session() as session:
        visit = session.get(HomeVisit, uuid.UUID(row['id']))
        assert visit.version == row['version'] and visit.quote_id is None
        assert session.query(HomeQuote).count() == 0
        assert session.execute(select(Booking.estimated_total).where(Booking.id == uuid.UUID(row['id']))).scalar() == 0


def reconciliation_body(client, row):
    quote = detail(client, row)['quote']
    photo = io.BytesIO()
    Image.new('RGB',(64,64),'white').save(photo,'PNG')
    response = client.post(f"/api/home/visits/{row['id']}/receipts",
        headers=headers('helper',uuid.uuid4().hex),data={'file':(io.BytesIO(photo.getvalue()),'receipt.png')})
    assert response.status_code == 201, response.json
    receipt_id = response.json['receipt']['id']
    return {'version': row['version'], 'quoteId': quote['id'], 'receiptsReviewed': True,
        'lines': [{'lineId': line['lineId'], 'actualCents': line['capCents'] - 100,
                   'receiptReference': receipt_id} for line in quote['materials']],
        'tax': {'amountCents': 700, 'reviewConfirmed': True, 'reviewReference': 'synthetic-final-tax-review'}}


def test_receipts_at_cost_with_unused_allowance_and_no_money_movement(app):
    client = app.test_client()
    row, _ = fully_approved(client)
    body = reconciliation_body(client, row)
    path = f"/visits/{row['id']}/materials/reconcile"
    assert post(client, path, body, 'helper').status_code == 403
    assert post(client, path, body).json['code'] == 'receipts_not_ready'
    # Service completion is a later stage. Seed only its status for this isolated
    # accounting acceptance; this is not evidence of a completed customer journey.
    with database.db_session() as session:
        session.execute(update(Booking).where(Booking.id == uuid.UUID(row['id'])).values(status='completed'))
    key = uuid.uuid4().hex
    result = post(client, path, body, key=key)
    assert result.status_code == 200
    assert post(client, path, body, key=key).json == result.json
    customer = detail(client, result.json)['quote']['reconciliation']
    assert customer['materialsActualCents'] == 2800 and customer['unusedAllowanceCents'] == 277
    assert customer['customerFinalCents'] == 15326 and 'helperActualPayCents' not in customer
    helper = detail(client, result.json, 'helper')['quote']['reconciliation']
    assert helper['helperActualPayCents'] == 11938
    with database.db_session() as session:
        assert session.query(HomeMaterialReconciliation).count() == 1
        assert session.execute(select(Booking.stripe_payment_intent_id).where(Booking.id == uuid.UUID(row['id']))).scalar() is None


@pytest.mark.parametrize('mutation', ['overspend', 'duplicate_line', 'missing_receipt', 'unreviewed', 'tax_exceeds_cap'])
def test_receipt_limits_and_review_cannot_be_bypassed(app, mutation):
    client = app.test_client()
    row, _ = fully_approved(client)
    with database.db_session() as session:
        session.execute(update(Booking).where(Booking.id == uuid.UUID(row['id'])).values(status='pending_confirmation'))
    body = reconciliation_body(client, row)
    if mutation == 'overspend': body['lines'][0]['actualCents'] = 2501
    elif mutation == 'duplicate_line': body['lines'][1]['lineId'] = body['lines'][0]['lineId']
    elif mutation == 'missing_receipt': body['lines'][0]['receiptReference'] = None
    elif mutation == 'unreviewed': body['receiptsReviewed'] = False
    elif mutation == 'tax_exceeds_cap': body['tax']['amountCents'] = 778
    assert post(client, f"/visits/{row['id']}/materials/reconcile", body).status_code == 400


def test_command_ensures_identity_without_rewriting_profile(app):
    client = app.test_client()
    assert client.get('/api/home/me', headers=headers()).status_code == 200
    with database.db_session() as session:
        session.execute(update(User).where(User.id == 'customer').values(name='Stored profile name'))
    assert create(client).status_code == 201
    with database.db_session() as session:
        assert session.execute(select(User.name).where(User.id == 'customer')).scalar() == 'Stored profile name'


def test_concurrent_rate_activation_cannot_overwrite_another_version(app):
    client = app.test_client()
    cards = [post(client, '/pricing', rates()).json['rateCardId'] for _ in range(2)]
    def publish(card):
        with app.test_client() as worker:
            return post(worker, f'/pricing/{card}/activate', {}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(publish, cards))
    assert sorted(results) == [200, 409]


def test_requote_and_helper_acceptance_do_not_deadlock_on_identity_fk(app, monkeypatch):
    client = app.test_client()
    row = prepared(client)
    card = activate(client)
    row = offer(client, row, card)
    current = detail(client, row)['quote']
    operator_locked, helper_started = threading.Event(), threading.Event()
    original = quotes.load_locked
    def coordinated(session, principal, booking_id, body, operator):
        if principal['uid'] == 'owner':
            loaded = original(session, principal, booking_id, body, operator)
            operator_locked.set()
            assert helper_started.wait(5)
            return loaded
        assert operator_locked.wait(5)
        # command() has already ensured the helper identity. It must not hold
        # an exclusive User row lock while it waits for the operator's booking.
        helper_started.set()
        return original(session, principal, booking_id, body, operator)
    monkeypatch.setattr(quotes, 'load_locked', coordinated)
    def reissue():
        with app.test_client() as worker:
            return post(worker, f"/visits/{row['id']}/quotes", offer_body(row, card)).status_code
    def accept():
        with app.test_client() as worker:
            return post(worker, f"/visits/{row['id']}/quotes/{current['id']}/accept",
                {'version': row['version'], 'digest': current['digest']}, 'helper').status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = pool.submit(reissue), pool.submit(accept)
        assert a.result() == 201 and b.result() == 409


@pytest.mark.parametrize('migration', ['001_booking_workflow.sql', '002_quotes.sql', '003_payments.sql',
                                       '004_customer_service.sql', '005_helper_calendar.sql', '006_operating_rules_draft.sql', '007_helper_availability.sql', '008_active_operating_policy.sql'])
def test_health_refuses_a_database_missing_the_required_home_migration(app, migration):
    client = app.test_client()
    assert client.get('/api/home/health').status_code == 200
    with database.db_session() as session:
        session.execute(text('DELETE FROM home_schema_migrations WHERE filename=:migration'), {'migration': migration})
    response = client.get('/api/home/health')
    assert response.status_code == 503 and response.json['code'] == 'temporary_error'
    assert response.headers['X-Request-ID'] == response.json['reference']


def test_completed_visit_issue_can_hold_and_resume_receipt_review(app):
    client = app.test_client()
    row, _ = fully_approved(client)
    with database.db_session() as session:
        session.execute(update(Booking).where(Booking.id == uuid.UUID(row['id'])).values(status='completed'))
    held = change(client, row, 'report_issue', uid='customer')
    assert held.status_code == 200
    row = held.json
    body = reconciliation_body(client, row)
    assert post(client, f"/visits/{row['id']}/materials/reconcile", body).json['code'] == 'receipts_not_ready'
    assert change(client, row, 'resolve_issue', uid='customer').status_code == 403
    row = change(client, row, 'resolve_issue').json
    assert post(client, f"/visits/{row['id']}/materials/reconcile", reconciliation_body(client, row)).status_code == 200


def test_quote_cannot_be_attached_to_another_households_visit(app):
    client = app.test_client()
    row, card = fully_approved(client)
    # Distinct households at non-overlapping times; this test exercises quote
    # ownership, not bypassing the helper calendar guard.
    another = create(client, {**payload(), 'time': '13:00'}, uid='another-customer').json
    another = change(client, another, 'review').json
    another = change(client, another, 'assign', helperId='helper').json
    another = change(client, another, 'accept', uid='helper').json
    another = offer(client, another, card)
    own_quote = detail(client, row)['quote']
    result = post(client, f"/visits/{another['id']}/quotes/{own_quote['id']}/approve",
        {'version': another['version'], 'digest': own_quote['digest']}, 'another-customer')
    assert result.json['code'] == 'quote_changed'
    assert client.get(f"/api/home/visits/{another['id']}/quotes/{own_quote['id']}", headers=headers('another-customer')).status_code == 404
    with pytest.raises(IntegrityError):
        with database.db_session() as session:
            session.execute(update(HomeVisit).where(HomeVisit.booking_id == uuid.UUID(another['id'])).values(quote_id=uuid.UUID(own_quote['id'])))
