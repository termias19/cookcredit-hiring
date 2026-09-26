from copy import deepcopy
from types import SimpleNamespace
import pytest
from flask import Flask
from itsdangerous import TimestampSigner
from middleware import auth
from routes import location as routes
from services import location


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setenv('LOCATION_TOKEN_SECRET', 'isolated-test-signing-secret-' * 2)
    monkeypatch.setenv('GOOGLE_GEOCODING_API_KEY', 'test-key-never-exposed')


@pytest.fixture
def google(monkeypatch):
    payload = {'status': 'OK', 'results': [{
        'address_components': [
            {'long_name': '30303', 'types': ['postal_code']},
            {'long_name': 'Atlanta', 'types': ['locality']},
            {'short_name': 'GA', 'types': ['administrative_area_level_1']},
            {'short_name': 'US', 'types': ['country']},
        ], 'geometry': {'location': {'lat': 33.75, 'lng': -84.39}},
    }]}
    calls = []
    def get(url, **kw):
        calls.append((url, kw))
        return SimpleNamespace(status_code=200, json=lambda: deepcopy(payload))
    monkeypatch.setattr(location.requests, 'get', get)
    return payload, calls


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(auth, '_verify_token', lambda token: {
        'uid': token, 'email_verified': token != 'unverified'})
    app = Flask(__name__)
    app.config.update(TESTING=True, RATELIMIT_ENABLED=False)
    app.register_blueprint(routes.location_bp, url_prefix='/location')
    return app.test_client()


def test_zip_lookup_is_country_limited_and_user_bound(google, client):
    response = client.post('/location/resolve', json={'postalCode': '30303', 'language': 'ES'},
                           headers={'Authorization': 'Bearer owner'})
    assert response.status_code == 200
    assert response.headers['Cache-Control'] == 'no-store'
    area = response.json['location']
    assert area['label'] == 'Atlanta, GA' and area['source'] == 'zip'
    assert not {'lat', 'lng', 'key'} & area.keys()
    assert 'test-key-never-exposed' not in response.text
    assert location.read_search_token(area['locationToken'], 'owner') == (33.75, -84.39)
    with pytest.raises(ValueError):
        location.read_search_token(area['locationToken'], 'other')
    call = google[1][0][1]
    assert call['params']['components'] == 'postal_code:30303|country:US'
    assert call['params']['language'] == 'es'
    assert call['timeout'] == (3, 8) and call['allow_redirects'] is False


def test_device_search_preserves_supplied_point_and_reports_accuracy(google):
    area = location.resolve_area({'lat': 33.751234, 'lng': -84.392345, 'accuracyMeters': 48}, 'owner')
    assert area['source'] == 'device' and area['accuracyMeters'] == 48
    assert location.read_search_token(area['locationToken'], 'owner') == (33.751234, -84.392345)
    assert google[1][0][1]['params']['result_type'] == 'postal_code'


@pytest.mark.parametrize('body', [None, [], {}, {'postalCode': 30303}, {'postalCode': '3030'},
    {'postalCode': '30303', 'lat': 33}, {'postalCode': '30303', 'extra': 1},
    {'lat': True, 'lng': 1, 'accuracyMeters': 1}, {'lat': 91, 'lng': 1, 'accuracyMeters': 1},
    {'lat': 1, 'lng': 181, 'accuracyMeters': 1}, {'lat': float('nan'), 'lng': 1, 'accuracyMeters': 1},
    {'lat': 1, 'lng': 1, 'accuracyMeters': float('inf')}, {'lat': 1, 'lng': 1, 'accuracyMeters': -1}])
def test_invalid_requests_never_call_google(body, google):
    with pytest.raises(ValueError):
        location.resolve_area(body, 'owner')
    assert not google[1]


@pytest.mark.parametrize('change', ['partial', 'country', 'zip', 'zero'])
def test_wrong_or_approximate_postal_matches_are_rejected(change, google):
    payload = google[0]
    if change == 'partial': payload['results'][0]['partial_match'] = True
    if change == 'country': payload['results'][0]['address_components'][3]['short_name'] = 'CA'
    if change == 'zip': payload['results'][0]['address_components'][0]['long_name'] = '30304'
    if change == 'zero': payload['status'] = 'ZERO_RESULTS'
    with pytest.raises(LookupError):
        location.resolve_area({'postalCode': '30303'}, 'owner')


def test_provider_failure_does_not_disclose_configuration(google, client):
    google[0].update(status='REQUEST_DENIED', error_message='sensitive-account-detail')
    response = client.post('/location/resolve', json={'postalCode': '30303'}, headers={'Authorization': 'Bearer owner'})
    assert response.status_code == 503
    assert 'sensitive-account-detail' not in response.text
    google[0].update(status='OK')
    google[0]['results'][0]['geometry'] = {}
    assert client.post('/location/resolve', json={'postalCode': '30303'}, headers={'Authorization': 'Bearer owner'}).status_code == 503


def test_token_expiry_tampering_and_email_requirement(monkeypatch, client, google):
    monkeypatch.setattr(TimestampSigner, 'get_timestamp', lambda _: 10000)
    token = location.search_token(user_id='owner', lat=1, lng=2)
    with pytest.raises(ValueError): location.read_search_token(token+'tampered', 'owner')
    monkeypatch.setattr(TimestampSigner, 'get_timestamp', lambda _: 11801)
    with pytest.raises(ValueError): location.read_search_token(token, 'owner')
    for bearer, expected in [(None, 401), ('unverified', 403)]:
        response = client.post('/location/resolve', json={'postalCode': '30303'},
                               headers={'Authorization': 'Bearer '+bearer} if bearer else {})
        assert response.status_code == expected
    assert not google[1]


def test_missing_configuration_fails_closed(monkeypatch, client):
    monkeypatch.delenv('GOOGLE_GEOCODING_API_KEY')
    response = client.post('/location/resolve', json={'postalCode': '30303'}, headers={'Authorization': 'Bearer owner'})
    assert response.status_code == 503


def test_public_profile_excludes_private_assessment_and_reviewer_details():
    from routes.cooks import _public_cook
    user = SimpleNamespace(id='cook', name='Cook', photo_url=None, dishes=[])
    cook = SimpleNamespace(to_dict=lambda: {'bio': 'Public bio', 'skillScore': 85,
        'skillTestResult': {'private': 'recording-reference'}, 'reviewNote': 'private-note',
        'stripeOnboarded': True, 'applicationStatus': 'approved'})
    result = _public_cook(user, cook)
    assert result['bio'] == 'Public bio' and result['skillScore'] == 85
    assert not {'skillTestResult', 'reviewNote', 'stripeOnboarded', 'applicationStatus'} & result.keys()
