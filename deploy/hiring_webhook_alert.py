"""Roll out retry-aware monitoring for the production Hiring webhook Scheduler job."""

import argparse
import copy
from datetime import datetime, timedelta, timezone
import json

from hiring_monitoring import application_error_filter
from hiring_staging import PROJECT, REGION, api, client

JOB = 'cc-hiring-webhooks'
SILENCE_SECONDS = 40 * 60
METRIC = 'cookcredit_hiring_webhook_success'
METRIC_TYPE = f'logging.googleapis.com/user/{METRIC}'
POLICY_NAME = 'CookCredit Hiring webhook dispatcher stalled'
LOG_METRICS = f'https://logging.googleapis.com/v2/projects/{PROJECT}/metrics'
MONITORING = f'https://monitoring.googleapis.com/v3/projects/{PROJECT}'
PROMQL = f'https://monitoring.googleapis.com/v1/projects/{PROJECT}/location/global/prometheus/api/v1/query'
SCHEDULER = f'https://cloudscheduler.googleapis.com/v1/projects/{PROJECT}/locations/{REGION}/jobs'

SCHEDULER_FILTER = (
    f'resource.type="cloud_scheduler_job" AND resource.labels.project_id="{PROJECT}" '
    'AND resource.labels.job_id=~"^cc-hiring-(emails|webhooks|expiry|dispatch)$" AND severity>=ERROR'
)
WEBHOOK_EXCLUSION = f' AND resource.labels.job_id!="{JOB}"'
SUCCESS_LOG_FILTER = (
    f'resource.type="cloud_scheduler_job" AND resource.labels.project_id="{PROJECT}" '
    f'AND resource.labels.location="{REGION}" AND resource.labels.job_id="{JOB}" '
    'AND log_id("cloudscheduler.googleapis.com/executions") '
    'AND jsonPayload."@type"="type.googleapis.com/google.cloud.scheduler.logging.AttemptFinished" '
    'AND httpRequest.status>=200 AND httpRequest.status<300 AND severity<ERROR'
)
METRIC_FILTER = (
    f'metric.type="{METRIC_TYPE}" AND resource.type="cloud_scheduler_job" '
    f'AND resource.labels.project_id="{PROJECT}" AND resource.labels.location="{REGION}" '
    f'AND resource.labels.job_id="{JOB}"'
)
ABSENCE_QUERY = (
    f'absent_over_time({{"{METRIC_TYPE}",monitored_resource="cloud_scheduler_job",'
    f'project_id="{PROJECT}",location="{REGION}",job_id="{JOB}"}}[{SILENCE_SECONDS // 60}m])'
)


def one_policy(policies, display_name, *, optional=False):
    matches = [policy for policy in policies if policy.get('displayName') == display_name]
    if not matches and optional:
        return None
    if len(matches) != 1:
        raise RuntimeError(f'Expected exactly one policy named {display_name}')
    return matches[0]


def validate_job(job):
    # Allow the five-minute cadence, four attempts at the full deadline, retry
    # backoffs of 15/30/60 seconds, and up to ten minutes of metric visibility lag.
    expected_retry = {
        'retryCount': 3, 'maxRetryDuration': '0s', 'minBackoffDuration': '15s',
        'maxBackoffDuration': '120s', 'maxDoublings': 5,
    }
    if (job.get('state') != 'ENABLED' or job.get('schedule') != '*/5 * * * *'
            or job.get('attemptDeadline') != '300s' or job.get('retryConfig') != expected_retry):
        raise RuntimeError('Review the silence window against the current Scheduler retry budget')


def scheduler_conditions(policy):
    conditions = copy.deepcopy(policy['conditions'])
    if len(conditions) != 1 or not policy.get('enabled') or not policy.get('notificationChannels'):
        raise RuntimeError('Expected the enabled production Scheduler alert with a notification channel')
    condition = conditions[0].get('conditionMatchedLog', {})
    if condition.get('filter') not in (SCHEDULER_FILTER, SCHEDULER_FILTER + WEBHOOK_EXCLUSION):
        raise RuntimeError('Production Scheduler filter changed outside this rollout')
    condition['filter'] = SCHEDULER_FILTER + WEBHOOK_EXCLUSION
    return conditions


def stalled_policy(channels):
    return {
        'displayName': POLICY_NAME,
        'enabled': True,
        'combiner': 'OR',
        'notificationChannels': channels,
        'userLabels': {'product': 'cookcredit-hiring', 'environment': 'production'},
        'conditions': [{
            'displayName': 'No successful production webhook dispatch for 40 minutes',
            'conditionPrometheusQueryLanguage': {
                'query': ABSENCE_QUERY, 'duration': '0s', 'evaluationInterval': '60s',
            },
        }],
        'documentation': {
            'mimeType': 'text/markdown',
            'content': ('The production cc-hiring-webhooks job has recorded no successful '
                        'execution for 40 minutes. Check Scheduler attempt logs and durable '
                        'webhook and billing queue counters. Review existing delivery state '
                        'before replaying work. The application alert still reports terminal '
                        'delivery failures and pending work at least ten minutes old.'),
        },
    }


def verify_replacement(policy, desired):
    for field in ('enabled', 'combiner', 'notificationChannels', 'userLabels'):
        if policy.get(field) != desired[field]:
            raise RuntimeError(f'Existing webhook alert has unexpected {field}')
    conditions = policy.get('conditions', [])
    actual = conditions[0].get('conditionPrometheusQueryLanguage', {}) if len(conditions) == 1 else {}
    if (actual.get('query') != ABSENCE_QUERY or actual.get('duration', '0s') != '0s'
            or actual.get('evaluationInterval') != '60s'):
        raise RuntimeError('Existing webhook alert has an unexpected condition')


def has_fresh_success(series, created, now):
    cutoff = max(created, now - timedelta(minutes=10))
    for stream in series:
        for point in stream.get('points', []):
            interval = point['interval']
            start = datetime.fromisoformat(interval['startTime'].replace('Z', '+00:00'))
            end = datetime.fromisoformat(interval['endTime'].replace('Z', '+00:00'))
            if cutoff <= start < end <= now and int(point['value'].get('int64Value', 0)) > 0:
                return True
    return False


def observed_success(session, since):
    now = datetime.now(timezone.utc)
    data = api(session, 'GET', f'{MONITORING}/timeSeries', params={
        'filter': METRIC_FILTER, 'interval.startTime': (now - timedelta(minutes=15)).isoformat(),
        'interval.endTime': now.isoformat(),
    })
    return has_fresh_success(data.get('timeSeries', []), since, now)


def run(session, phase):
    if phase not in ('plan', 'prepare', 'activate'):
        raise ValueError('Unknown rollout phase')
    validate_job(api(session, 'GET', f'{SCHEDULER}/{JOB}'))
    page = api(session, 'GET', f'{MONITORING}/alertPolicies', params={'pageSize': 100})
    if page.get('nextPageToken'):
        raise RuntimeError('Review the complete list of alert policies before changing coverage')
    policies = page['alertPolicies']
    current = one_policy(policies, 'CookCredit hiring production background job failure')
    conditions = scheduler_conditions(current)
    delivery = one_policy(policies, 'CookCredit hiring production application and delivery failures')
    if (not delivery.get('enabled') or delivery.get('notificationChannels') != current['notificationChannels']
            or [c.get('conditionMatchedLog', {}).get('filter') for c in delivery['conditions']]
            != [application_error_filter('production')]):
        raise RuntimeError('Verify the existing production webhook queue alert before changing coverage')

    desired = stalled_policy(current['notificationChannels'])
    replacement = one_policy(policies, POLICY_NAME, optional=True)
    if replacement:
        verify_replacement(replacement, desired)
    metric = api(session, 'GET', f'{LOG_METRICS}/{METRIC}', missing=True)
    if metric and (metric.get('filter') != SUCCESS_LOG_FILTER or metric.get('disabled')
                   or metric.get('metricDescriptor', {}).get('metricKind') != 'DELTA'
                   or metric.get('metricDescriptor', {}).get('valueType') != 'INT64'
                   or metric.get('metricDescriptor', {}).get('labels') or metric.get('bucketName')):
        raise RuntimeError('Existing webhook success metric does not match the intended filter')

    outcome = {'phase': phase, 'job': JOB, 'silenceSeconds': SILENCE_SECONDS,
               'schedulerPolicy': current['name'], 'queuePolicy': delivery['name'],
               'stalledPolicy': replacement['name'] if replacement else None, 'metricPresent': bool(metric)}
    if phase == 'plan':
        return outcome
    if phase == 'prepare':
        if not metric:
            metric = api(session, 'POST', LOG_METRICS, json={
                'name': METRIC, 'filter': SUCCESS_LOG_FILTER,
                'description': 'Successful completed attempts of the production Hiring webhook Scheduler job.',
            })
        if not replacement:
            # Cloud Logging can accept the metric before Monitoring can use it
            # in a condition. The original alert remains active during that gap.
            descriptor = api(session, 'GET', f'{MONITORING}/metricDescriptors/{METRIC_TYPE}', missing=True)
            if not descriptor:
                return {**outcome, 'metricPresent': True, 'waitingForMetricDescriptor': True}
            since = datetime.fromisoformat(metric['createTime'].replace('Z', '+00:00'))
            if not observed_success(session, since):
                return {**outcome, 'metricPresent': True, 'waitingForSuccessMetric': True}
            evaluation = api(session, 'GET', PROMQL, params={'query': ABSENCE_QUERY})
            if evaluation.get('status') != 'success' or evaluation.get('data', {}).get('result') != []:
                raise RuntimeError('The alert query must see the live successful dispatch before arming')
            replacement = api(session, 'POST', f'{MONITORING}/alertPolicies', json=desired)
            verify_replacement(replacement, desired)
        return {**outcome, 'stalledPolicy': replacement['name'], 'metricPresent': True}

    if not replacement or not metric:
        raise RuntimeError('Prepare the replacement monitor before activating the filter')
    created = datetime.fromisoformat(replacement['mutationRecord']['mutateTime'].replace('Z', '+00:00'))
    if not observed_success(session, created):
        return {**outcome, 'activated': False, 'waitingForSuccessMetric': True}
    if conditions != current['conditions']:
        api(session, 'PATCH', 'https://monitoring.googleapis.com/v3/' + current['name'],
            params={'updateMask': 'conditions'}, json={'name': current['name'], 'conditions': conditions})
    after = api(session, 'GET', 'https://monitoring.googleapis.com/v3/' + current['name'])
    if after['conditions'] != conditions or any(
        after.get(field) != current.get(field)
        for field in ('enabled', 'notificationChannels', 'alertStrategy', 'documentation', 'userLabels', 'combiner')
    ):
        raise RuntimeError('Unexpected changes in the Scheduler alert readback')
    return {**outcome, 'activated': True, 'verifiedSuccessMetric': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=('plan', 'prepare', 'activate'), default='plan')
    phase = parser.parse_args().phase
    with client() as session:
        print(json.dumps(run(session, phase), indent=2))
