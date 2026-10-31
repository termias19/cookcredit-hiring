"""Calendar integrity over real disposable SQL; no account/provider impersonation."""
import uuid
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select, update, func
from sqlalchemy.orm import sessionmaker
from models import Booking
from models.home_service import HomeVisit, HomeEvent
from services import database, home_visits
from tests.test_home_visits import app, home_db, headers, payload, create, change, seed_helper


def requested(client, *, uid='customer', **fields):
    response = create(client, {**payload(), **fields}, uid=uid)
    assert response.status_code == 201, response.json
    result = change(client, response.json, 'review')
    assert result.status_code == 200, result.json
    return result.json


def assign(client, row, helper='helper', uid='owner'):
    return change(client, row, 'assign', uid=uid, helperId=helper)


def test_overlapping_assignment_is_private_and_does_not_change_the_visit(app):
    c = app.test_client(); seed_helper(c)
    first = requested(c)
    assert assign(c, first).status_code == 200
    second = requested(c, uid='other-household', time='11:00')
    denied = assign(c, second)
    assert denied.status_code == 409 and denied.json['code'] == 'helper_schedule_conflict'
    assert first['id'] not in str(denied.json) and payload()['address'] not in str(denied.json)
    with database.db_session() as session:
        assert session.execute(select(Booking.cook_id).where(Booking.id == uuid.UUID(second['id']))).scalar_one() is None
        assert session.get(HomeVisit, uuid.UUID(second['id'])).version == second['version']
        assert session.execute(select(func.count(HomeEvent.id)).where(
            HomeEvent.booking_id == uuid.UUID(second['id']), HomeEvent.action == 'assign')).scalar_one() == 0


def test_adjacent_visits_and_different_helpers_remain_available(app):
    c = app.test_client(); seed_helper(c); seed_helper(c, uid='second-helper')
    assert assign(c, requested(c)).status_code == 200  # 10:00 through 12:30.
    assert assign(c, requested(c, time='12:30')).status_code == 200
    assert assign(c, requested(c, time='11:00'), helper='second-helper').status_code == 200


def test_cancellation_releases_the_helper_time(app):
    c = app.test_client(); seed_helper(c)
    first = assign(c, requested(c)).json
    second = requested(c)
    assert assign(c, second).status_code == 409
    assert change(c, first, 'cancel').status_code == 200
    assert assign(c, second).status_code == 200


def test_completed_visit_does_not_keep_reserving_helper_time(app):
    c = app.test_client(); seed_helper(c)
    first = assign(c, requested(c)).json
    with database.db_session() as session:
        # Historical completed fixture, not a financial state-machine shortcut.
        session.execute(update(Booking).where(Booking.id == uuid.UUID(first['id'])).values(status='completed'))
    assert assign(c, requested(c)).status_code == 200


def test_simultaneous_operators_cannot_assign_the_same_time_twice(app, monkeypatch):
    c = app.test_client(); seed_helper(c)
    c.get('/api/home/me', headers=headers('operator'))
    first = requested(c); second = requested(c, uid='other-household')
    barrier = threading.Barrier(2)
    permission = home_visits.helper_allowed
    def competing_permission(session, uid, service, *, lock=False):
        if lock:
            barrier.wait(timeout=10)
        return permission(session, uid, service, lock=lock)
    monkeypatch.setattr(home_visits, 'helper_allowed', competing_permission)
    def send(item):
        row, actor = item
        with app.test_client() as client:
            response = assign(client, row, uid=actor)
            return response.status_code, response.json
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(send, [(first, 'owner'), (second, 'operator')]))
    assert sorted(code for code, _ in results) == [200, 409]
    assert next(body for code, body in results if code == 409)['code'] == 'helper_schedule_conflict'
    with database.db_session() as session:
        assert session.execute(select(func.count(Booking.id)).where(Booking.cook_id == 'helper')).scalar_one() == 1


def test_acceptance_rechecks_conflicts_in_preexisting_assignments(app):
    c = app.test_client(); seed_helper(c)
    first = assign(c, requested(c)).json
    second = requested(c)
    with database.db_session() as session:
        # Model data created before the calendar guard was deployed.
        session.execute(update(Booking).where(Booking.id == uuid.UUID(second['id'])).values(cook_id='helper'))
    denied = change(c, first, 'accept', uid='helper')
    assert denied.status_code == 409 and denied.json['code'] == 'helper_schedule_conflict'
    assert change(c, second, 'cancel').status_code == 200
    assert change(c, first, 'accept', uid='helper').status_code == 200


def test_calendar_uses_stored_timezones_instead_of_wall_clock_labels(app, monkeypatch):
    c = app.test_client(); seed_helper(c)
    local = requested(c)
    assert assign(c, local).status_code == 200
    day = date.fromisoformat(payload()['date'])
    same_instant = datetime.combine(day, time(10), ZoneInfo('America/New_York')).astimezone(timezone.utc)
    monkeypatch.setenv('HOME_SERVICE_TIMEZONE', 'UTC')
    second = requested(c, date=same_instant.date().isoformat(), time=same_instant.strftime('%H:%M'))
    assert assign(c, second).status_code == 409


def test_visit_that_crosses_midnight_blocks_next_day_overlap(app):
    c = app.test_client(); seed_helper(c)
    assert assign(c, requested(c, time='23:00', durationMinutes=480)).status_code == 200
    following = date.fromisoformat(payload()['date']) + timedelta(days=1)
    second = requested(c, date=following.isoformat(), time='06:00')
    assert assign(c, second).status_code == 409


def test_calendar_rejects_an_isolation_level_that_can_hide_a_waited_assignment(app, home_db, monkeypatch):
    c = app.test_client(); seed_helper(c)
    row = requested(c)
    configured = home_db.execution_options(isolation_level='REPEATABLE READ')
    monkeypatch.setattr(database, 'SessionLocal', sessionmaker(bind=configured, expire_on_commit=False))
    denied = assign(c, row)
    assert denied.status_code == 503 and denied.json['code'] == 'calendar_unavailable'
