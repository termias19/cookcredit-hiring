"""Safe diagnosis preserves retry/alerts without copying household data."""
import json
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
