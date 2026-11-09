from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hiring_webhook_alert as alert


def test_only_production_webhook_attempts_leave_the_immediate_scheduler_rule():
    policy = {'enabled': True, 'notificationChannels': ['owner-channel'], 'conditions': [{
        'name': 'existing-condition',
        'conditionMatchedLog': {'filter': alert.SCHEDULER_FILTER, 'labelExtractors': {'job': 'EXTRACT(resource.labels.job_id)'}},
    }]}
    changed = alert.scheduler_conditions(policy)
    assert changed[0]['name'] == policy['conditions'][0]['name']
    assert changed[0]['conditionMatchedLog']['labelExtractors'] == policy['conditions'][0]['conditionMatchedLog']['labelExtractors']
    assert changed[0]['conditionMatchedLog']['filter'] == alert.SCHEDULER_FILTER + ' AND resource.labels.job_id!="cc-hiring-webhooks"'
    assert policy['conditions'][0]['conditionMatchedLog']['filter'] == alert.SCHEDULER_FILTER
    policy['conditions'] = changed
    assert alert.scheduler_conditions(policy) == changed
    policy['conditions'][0]['conditionMatchedLog']['filter'] += ' AND severity>=CRITICAL'
    with pytest.raises(RuntimeError, match='changed outside'):
        alert.scheduler_conditions(policy)


def test_cutover_requires_a_positive_sample_after_the_policy_exists():
    now = datetime(2026, 11, 9, 15, 30, tzinfo=timezone.utc)
    created = now - timedelta(minutes=8)

    def series(start, value):
        return [{'points': [{
            'interval': {'startTime': start.isoformat(), 'endTime': (start + timedelta(minutes=1)).isoformat()},
            'value': {'int64Value': str(value)},
        }]}]

    assert not alert.has_fresh_success([], created, now)
    assert not alert.has_fresh_success(series(created - timedelta(seconds=1), 1), created, now)
    assert not alert.has_fresh_success(series(created + timedelta(minutes=1), 0), created, now)
    assert not alert.has_fresh_success(series(now, 1), created, now)
    assert alert.has_fresh_success(series(created + timedelta(minutes=1), 1), created, now)


def test_changed_retry_deadline_requires_review():
    job = {'state': 'ENABLED', 'schedule': '*/5 * * * *', 'attemptDeadline': '300s',
           'retryConfig': {'retryCount': 3, 'maxRetryDuration': '0s', 'minBackoffDuration': '15s',
                           'maxBackoffDuration': '120s', 'maxDoublings': 5}}
    alert.validate_job(job)
    with pytest.raises(RuntimeError, match='retry budget'):
        alert.validate_job({**job, 'attemptDeadline': '600s'})
