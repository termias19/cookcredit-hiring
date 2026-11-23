"""Postal snapshots and repeat preferences use the existing private visit only."""
import copy
import uuid
import pytest
from sqlalchemy import select, func
from models import Booking, EaterProfile
from models.home_service import HomeVisit
from services import database, home_visits as visits
from tests.test_home_visits import app, home_db, headers, payload, create


ADDRESS = {'street':'100 Example Street','unit':'Unit 2','city':'Atlanta',
           'state':'GA','postalCode':'30315','country':'US'}
FORMATTED = '100 Example Street, Unit 2, Atlanta, GA 30315'


@pytest.mark.parametrize('change', [
    {'postalCode':'303'}, {'country':'CA'}, {'city':'Atlanta\nPRIVATE'},
    {'lat':33.5}, {'verified':True}, {'street':''}, {'unit':None}, {'state':'ZZ'},
])
def test_postal_fields_are_strict_and_cannot_claim_verified_location(change):
    with pytest.raises(visits.HomeError):
        visits.address_details({**ADDRESS,**change})


def test_address_normalizes_whitespace_and_optional_unit_without_geocoding():
    details, formatted = visits.address_details({**ADDRESS,'state':'ga','country':'us','unit':' '})
    assert details == {**ADDRESS,'unit':''}
    assert formatted == '100 Example Street, Atlanta, GA 30315'


@pytest.mark.parametrize('value', ['daily', {}, None, True])
def test_invalid_repeat_preferences_are_rejected(value):
    with pytest.raises(visits.HomeError) as rejected:
        visits.validate_request({**payload(), 'repeatPreference':value})
    assert rejected.value.code == 'invalid_repeat_preference'


def test_address_and_display_cannot_disagree():
    with pytest.raises(visits.HomeError) as rejected:
        visits.validate_request({**payload(),'addressDetails':ADDRESS})
    assert rejected.value.code == 'invalid_address'


def test_repeat_request_is_one_idempotent_private_visit_not_a_series(app):
    client = app.test_client()
    body = {**payload(),'address':FORMATTED,'addressDetails':ADDRESS,'repeatPreference':'weekly'}
    key = uuid.uuid4().hex
    first = create(client,body,key)
    assert first.status_code == 201, first.json
    assert create(client,body,key).json == first.json
    path = '/api/home/visits/' + first.json['id']
    for uid in ('customer','owner'):
        detail = client.get(path,headers=headers(uid)).json
        assert detail['address'] == FORMATTED
        assert detail['instructions']['addressDetails'] == ADDRESS
        assert detail['instructions']['repeatPreference'] == 'weekly'
    assert client.get(path,headers=headers('stranger')).status_code == 404
    listing = client.get('/api/home/visits',headers=headers()).json['visits']
    assert len(listing) == 1 and 'instructions' not in listing[0] and 'address' not in listing[0]
    with database.db_session() as session:
        assert session.scalar(select(func.count()).select_from(Booking)) == 1
        assert session.scalar(select(func.count()).select_from(HomeVisit)) == 1


def test_saved_address_round_trip_and_forget_clear_the_existing_private_fields(app):
    client = app.test_client()
    body = {'address':FORMATTED,'addressDetails':ADDRESS,'instructions':payload()['instructions'],'remember':True}
    saved = client.put('/api/home/household',json=body,headers=headers(key=uuid.uuid4().hex))
    assert saved.status_code == 200, saved.json
    assert client.get('/api/home/household',headers=headers()).json['household']['addressDetails'] == ADDRESS
    assert client.get('/api/home/household',headers=headers('stranger')).json['household'] is None
    with database.db_session() as session:
        row = session.execute(select(EaterProfile.address_city,EaterProfile.address_state,EaterProfile.address_zip)).one()
        assert tuple(row) == ('Atlanta','GA','30315')
    # An older client can still save free text, without retaining stale metadata.
    legacy = copy.deepcopy(body); legacy.pop('addressDetails'); legacy['address'] = 'Updated legacy address'
    assert client.put('/api/home/household',json=legacy,headers=headers(key=uuid.uuid4().hex)).status_code == 200
    assert client.get('/api/home/household',headers=headers()).json['household']['addressDetails'] is None
    assert client.delete('/api/home/household',json={},headers=headers(key=uuid.uuid4().hex)).status_code == 200
    with database.db_session() as session:
        assert tuple(session.execute(select(EaterProfile.address_street,EaterProfile.address_city,
            EaterProfile.address_state,EaterProfile.address_zip)).one()) == (None,None,None,None)


def test_customer_cannot_submit_a_structured_address_outside_the_default_service_state(app):
    client=app.test_client();address={**ADDRESS,'state':'CA','postalCode':'90001'}
    response=create(client,{**payload(),'addressDetails':address,'address':'100 Example Street, Unit 2, Atlanta, CA 90001'})
    assert response.status_code==400 and response.json['code']=='invalid_address'
    assert client.get('/api/home/visits',headers=headers()).json['visits']==[]
