"""Recovery never conceals a later failure, stale counters or the legacy blocker."""
import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location('platform_monitoring', Path(__file__).parents[1] / 'platform_monitoring.py')
monitor = importlib.util.module_from_spec(spec); spec.loader.exec_module(monitor)
NOW = datetime(2026, 11, 8, 20, tzinfo=timezone.utc)


def attempt(seconds, status, job='cc-hiring-emails'):
    return {'timestamp': (NOW - timedelta(seconds=seconds)).isoformat(),
            'resource': {'labels': {'job_id': job}}, 'httpRequest': {'status': status},
            'jsonPayload': {'@type': monitor.FINISHED, 'private': 'never print this'}}


def test_later_success_recovers_transport_but_newer_failure_stays_unrecovered():
    config = {'state': 'ENABLED', 'status': {'code': 0}}
    entries = [attempt(90, 503), attempt(60, 200)]
    result = monitor.summarize_job(entries, config, 60, NOW)
    assert result['state'] == 'healthy' and result['recoveredAttempts'] == 1
    entries.append(attempt(10, 502))
    result = monitor.summarize_job(entries, config, 60, NOW)
    assert result['state'] == 'attention_required' and result['unrecoveredAttempts'] == 1
    assert 'never print this' not in json.dumps(result)


@pytest.mark.parametrize('entries,config', [([], {'state': 'ENABLED'}),
    ([attempt(4000, 200)], {'state': 'ENABLED'}),
    ([attempt(1, 200)], {'state': 'PAUSED'}),
    ([attempt(1, 200)], {'state': 'ENABLED', 'status': {'code': 13}}),
    ([attempt(-1, 200)], {'state': 'ENABLED'})])
def test_missing_stale_paused_and_conflicting_evidence_fail_closed(entries, config):
    assert monitor.summarize_job(entries, config, 60, NOW)['state'] == 'attention_required'


def fake_cloud(*, missing_queue=False, billing=True, legacy=False):
    calls = []
    def api(session, method, url, **kwargs):
        calls.append((method, url))
        assert method == 'GET' or (method == 'POST' and url == monitor.LOG_API)
        if url.endswith('/instances/cookcredit-db'):
            assert legacy
            return {'settings': {'activationPolicy': 'NEVER'}}
        if '/services/' in url:
            return {'template': {'containers': [{'env': [{'name': 'STRIPE_ASYNC_ENABLED', 'value': '1' if billing else '0'}]}]}}
        if '/jobs/' in url:
            return {'state': 'ENABLED', 'status': {'code': 0}}
        if url == monitor.LOG_API:
            body = kwargs['json']
            if 'queue_health' not in body['filter']:
                project = body['resourceNames'][0].split('/')[-1]
                return {'entries': [attempt(60, 200, name) for p, name, _ in monitor.job_specs('production', legacy) if p == project]}
            entries = []
            for service, queues in (('cookcredit-hiring', ('email', 'webhook', 'billing') if billing else ('email', 'webhook')),
                                    ('cookcredit-home', ('email', 'home_financial', 'home_events'))):
                for queue in queues:
                    if missing_queue and queue == 'home_events':
                        continue
                    entries.append({'timestamp': (NOW - timedelta(seconds=30)).isoformat(), 'severity': 'INFO',
                        'resource': {'labels': {'service_name': service}},
                        'jsonPayload': {'event': 'queue_health', 'queue': queue, 'failed': 0, 'pending': 0,
                            'oldestSeconds': 0, 'held': 0, 'expiredLeases': 0, 'paymentReviews': 0,
                            'expectedWaiting': 0, 'expectedWaitingOldestSeconds': 0, 'expectedWaitingOverdue': False,
                            'private': 'never print this'}})
            return {'entries': entries}
        pytest.fail('Unexpected Cloud API')
    return api, calls


@pytest.mark.parametrize('billing', [False, True])
def test_review_reads_existing_configuration_and_only_safe_counters(billing):
    api, calls = fake_cloud(billing=billing)
    result = monitor.review(None, api, 'production', now=NOW)
    assert result['passed'] and result['readOnly']
    assert result['hiringAsyncBillingEnabled'] == billing
    assert len(result['queues']) == (6 if billing else 5)
    assert 'never print this' not in json.dumps(result)
    assert all(method == 'GET' or url == monitor.LOG_API for method, url in calls)


def test_disabled_legacy_database_is_a_visible_blocker_without_connection_or_restart():
    api, calls = fake_cloud(legacy=True)
    result = monitor.review(None, api, 'production', include_shared=True, now=NOW)
    legacy = next(j for j in result['jobs'] if j['job'] == 'biometric-retention-sweep')
    assert legacy['state'] == 'blocked_database_disabled' and legacy['requiresDataDisposition']
    assert not result['passed']
    assert sum('/instances/' in url for _, url in calls) == 1


def test_missing_queue_or_incomplete_logs_never_pass():
    api, _ = fake_cloud(missing_queue=True)
    assert not monitor.review(None, api, 'production', now=NOW)['passed']
    with pytest.raises(RuntimeError, match='Incomplete monitoring evidence'):
        monitor.read_pages(None, lambda *a, **kw: {'nextPageToken': 'private-page-token'},
                           'POST', monitor.LOG_API, 'entries', pages=1)


def test_dashboard_contains_failure_recovery_and_validation_views_without_new_alerts():
    dashboard = monitor.dashboard()
    assert dashboard['displayName'] == monitor.DASHBOARD_TITLE
    filters = [w['logsPanel']['filter'] for w in dashboard['gridLayout']['widgets'] if 'logsPanel' in w]
    assert any('home_request_rejected' in q for q in filters)
    assert any('httpRequest.status=200' in q for q in filters)
    assert any('severity>=ERROR' in q for q in filters)
    assert any('biometric-retention-sweep' in q for q in filters)
    assert 'notificationChannels' not in json.dumps(dashboard)
