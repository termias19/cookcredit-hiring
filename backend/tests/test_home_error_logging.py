"""Safe diagnosis preserves retry/alerts without copying household data."""
import json
import pytest
from flask import request
from home_app import create_app
from services import home_visits as visits
from tests.test_home_visits import app,home_db,create


def test_expected_server_failure_has_safe_code_method_and_matching_reference(app,monkeypatch,capsys):
    def broken(*args,**kwargs):
        raise visits.HomeError('receipt_store_unavailable','private@example.test Synthetic household note',503)
    monkeypatch.setattr(visits,'event',broken)
    response=create(app.test_client());assert response.status_code==503
    assert response.headers['Retry-After']=='5'
    output=capsys.readouterr().out
    records=[json.loads(line)for line in output.splitlines()if line.startswith('{')]
    failure=next(row for row in records if row['event']=='home_request_failed')
    assert failure['code']=='receipt_store_unavailable' and failure['method']=='POST'
    assert failure['requestId']==response.headers['X-Request-ID']
    assert failure['severity']=='ERROR' and failure['status']==503
    assert 'private@example.test'not in output and 'Synthetic household note'not in output


@pytest.mark.parametrize('status,code', [(400, 'invalid_address'), (409, 'slot_unavailable'),
    (422, 'invalid_schedule'), (429, 'try_later'), (400, 'private@example.test')])
def test_rejected_request_is_diagnosable_without_household_or_identity_data(monkeypatch,capsys,status,code):
    monkeypatch.setenv('RELEASE_COMMIT', 'a' * 40)
    app = create_app({'TESTING': True, 'HOME_ENABLED': True, 'RATELIMIT_ENABLED': False})

    @app.post('/diagnostic/<private_id>')
    def rejected(private_id):
        assert request.json['address'] == 'Synthetic sensitive street'
        raise visits.HomeError(code, 'private@example.test Synthetic household note', status)

    response = app.test_client().post('/diagnostic/private-person?phone=4045550123',
        json={'address': 'Synthetic sensitive street', 'health': 'Synthetic medical note'},
        headers={'Authorization': 'Bearer private-token', 'X-Request-ID': 'untrusted-reference'})
    assert response.status_code == status
    reference = response.headers['X-Request-ID']
    assert response.json['reference'] == reference and len(reference) == 32
    output = capsys.readouterr().out
    records = [json.loads(line) for line in output.splitlines() if line.startswith('{')]
    diagnostic = next(row for row in records if row['event'] == 'home_request_rejected')
    assert diagnostic['code'] == (code if '@' not in code else 'invalid_domain_code')
    assert diagnostic['severity'] == 'WARNING' and diagnostic['status'] == status
    assert diagnostic['requestId'] == reference and diagnostic['commit'] == 'a' * 40
    assert diagnostic['endpoint'] == 'rejected' and diagnostic['method'] == 'POST'
    assert not any(row['event'] == 'home_request_failed' for row in records)
    for private in ('private@example.test', 'Synthetic household note', 'Synthetic sensitive street',
                    'Synthetic medical note', 'private-person', '4045550123', 'private-token', 'untrusted-reference'):
        assert private not in output


def test_malformed_json_has_a_fixed_reason_and_server_reference(capsys):
    app = create_app({'TESTING': True, 'HOME_ENABLED': True, 'RATELIMIT_ENABLED': False})

    @app.post('/diagnostic-json')
    def diagnostic_json():
        return request.get_json()

    response = app.test_client().post('/diagnostic-json', data='{"secret":"private-token",',
        content_type='application/json')
    assert response.status_code == 400
    assert response.json['reference'] == response.headers['X-Request-ID']
    output = capsys.readouterr().out
    records = [json.loads(line) for line in output.splitlines() if line.startswith('{')]
    assert next(row for row in records if row['event'] == 'home_request_rejected')['code'] == 'http_400'
    assert 'private-token' not in output
