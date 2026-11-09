"""Read-only recovery review of existing CookCredit jobs and durable queue counters.

No database connection, dispatch, message replay or payment call is made. A later
successful job invocation means transport recovered; delivery still needs healthy
durable queue counters. Missing, stale or truncated evidence never means healthy.
"""
import argparse
from datetime import datetime, timedelta, timezone
import json

PROJECT = 'cookcredit-scoring'
SHARED_PROJECT = 'foodnlit-1123e'
LOG_API = 'https://logging.googleapis.com/v2/entries:list'
FINISHED = 'type.googleapis.com/google.cloud.scheduler.logging.AttemptFinished'
DASHBOARD_TITLE = 'CookCredit operations and recovery'


def job_specs(environment, include_shared=False):
    if environment not in ('staging', 'production'):
        raise ValueError('Explicit production or staging environment required')
    prefix = 'cc-hiring-' + ('stg-' if environment == 'staging' else '')
    specs = [(PROJECT, prefix + kind, 60 if kind == 'emails' else 300)
             for kind in ('emails', 'webhooks', 'expiry', 'dispatch')]
    specs.append((PROJECT, 'cc-home-' + ('stg' if environment == 'staging' else 'prod') + '-recovery', 600))
    if include_shared:
        specs.extend([(SHARED_PROJECT, 'firebase-schedule-purgeExpiredCookCreditSkillData-us-central1', 3600),
                      (PROJECT, 'biometric-retention-sweep', 86400)])
    return specs


def parse_time(value):
    try:
        stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return stamp.astimezone(timezone.utc) if stamp.tzinfo else None
    except (AttributeError, TypeError, ValueError):
        return None


def summarize_job(entries, config, cadence, now):
    attempts = []
    for row in entries:
        if row.get('jsonPayload', {}).get('@type') != FINISHED:
            continue
        stamp = parse_time(row.get('timestamp'))
        status = row.get('httpRequest', {}).get('status')
        if stamp is None:
            continue
        status = status if type(status) is int and 100 <= status <= 599 else None
        if row.get('severity') in ('ERROR', 'CRITICAL', 'ALERT', 'EMERGENCY'):
            outcome = 'failed'
        elif status is None:
            outcome = 'unknown'
        else:
            outcome = 'succeeded' if 200 <= status < 300 else 'failed'
        attempts.append((stamp, status, outcome))
    attempts.sort(key=lambda attempt: (attempt[0], attempt[2] != 'succeeded'), reverse=True)
    success = next((stamp for stamp, _, outcome in attempts if outcome == 'succeeded'), None)
    failures = [stamp for stamp, _, outcome in attempts if outcome == 'failed']
    # Do not confuse a running/newer failure with an earlier successful call.
    recovered = sum(success is not None and stamp < success for stamp in failures)
    latest_time, latest_status, latest_outcome = attempts[0] if attempts else (None, None, 'unknown')
    fresh = latest_time is not None and 0 <= (now - latest_time).total_seconds() <= max(900, cadence * 2)
    healthy = (config.get('state') == 'ENABLED' and fresh and latest_outcome == 'succeeded'
               and config.get('status', {}).get('code', 0) == 0)
    return {'state': 'healthy' if healthy else 'attention_required',
            'schedulerState': config.get('state'), 'lastHttpStatus': latest_status, 'lastOutcome': latest_outcome,
            'lastAttempt': latest_time.isoformat() if latest_time else None,
            'lastSuccess': success.isoformat() if success else None,
            'failedAttempts': len(failures), 'recoveredAttempts': recovered,
            'unrecoveredAttempts': len(failures) - recovered,
            'unknownAttempts': sum(outcome == 'unknown' for _, _, outcome in attempts), 'fresh': fresh}


def read_pages(session, api, method, url, key, *, body=None, pages=20):
    result = []; token = None
    for _ in range(pages):
        payload = {**(body or {}), 'pageSize': 1000}
        if token:
            payload['pageToken'] = token
        data = api(session, method, url, **({'json': payload} if method == 'POST' else {'params': payload}))
        result.extend(data.get(key, []))
        token = data.get('nextPageToken')
        if not token:
            return result
    raise RuntimeError('Incomplete monitoring evidence')


def review(session, api, environment, *, hours=24, include_shared=False, now=None):
    if type(hours) is not int or not 2 <= hours <= 48:
        raise ValueError('Review window must be 2 to 48 hours')
    now = now or datetime.now(timezone.utc)
    # All log reads use the same cutoff. A healthy queue report emitted while
    # this multi-request review is running must not look like a future log.
    snapshot = ' AND timestamp<="' + now.isoformat() + '"'
    specs = job_specs(environment, include_shared)
    jobs = []
    for project in sorted({p for p, _, _ in specs}):
        names = [name for p, name, _ in specs if p == project]
        query = ('resource.type="cloud_scheduler_job" AND timestamp>="' + (now - timedelta(hours=hours)).isoformat()
                 + '" AND jsonPayload."@type"="' + FINISHED + '" AND resource.labels.job_id=('
                 + ' OR '.join('"' + n + '"' for n in names) + ')' + snapshot)
        entries = read_pages(session, api, 'POST', LOG_API, 'entries', body={
            'resourceNames': ['projects/' + project], 'filter': query, 'orderBy': 'timestamp desc'})
        for p, name, cadence in specs:
            if p != project:
                continue
            config = api(session, 'GET', 'https://cloudscheduler.googleapis.com/v1/projects/'
                         + p + '/locations/us-central1/jobs/' + name)
            own = [e for e in entries if e.get('resource', {}).get('labels', {}).get('job_id') == name]
            result = {'project': p, 'job': name, **summarize_job(own, config, cadence, now)}
            if name == 'biometric-retention-sweep':
                sql = api(session, 'GET', 'https://sqladmin.googleapis.com/sql/v1beta4/projects/' + PROJECT + '/instances/cookcredit-db')
                if sql.get('settings', {}).get('activationPolicy') == 'NEVER':
                    result.update(state='blocked_database_disabled', requiresDataDisposition=True)
            jobs.append(result)

    suffix = '-staging' if environment == 'staging' else ''
    services = ('cookcredit-hiring' + suffix, 'cookcredit-home' + suffix)
    hiring = api(session, 'GET', 'https://run.googleapis.com/v2/projects/' + PROJECT
                 + '/locations/us-central1/services/' + services[0])
    billing_enabled = any(e.get('name') == 'STRIPE_ASYNC_ENABLED' and e.get('value') == '1'
                          for c in hiring.get('template', {}).get('containers', []) for e in c.get('env', []))
    query = ('resource.type="cloud_run_revision" AND resource.labels.service_name=('
             + ' OR '.join('"' + s + '"' for s in services) + ') AND jsonPayload.event="queue_health"'
             + ' AND timestamp>="' + (now - timedelta(hours=2)).isoformat() + '"' + snapshot)
    entries = read_pages(session, api, 'POST', LOG_API, 'entries', body={
        'resourceNames': ['projects/' + PROJECT], 'filter': query, 'orderBy': 'timestamp desc'}, pages=5)
    expected = {(services[0], q) for q in ('email', 'webhook')} | {
        (services[1], q) for q in ('email', 'home_events', 'home_financial')}
    if billing_enabled:
        expected.add((services[0], 'billing'))
    latest = {}
    for e in entries:
        j = e.get('jsonPayload', {}); service = e.get('resource', {}).get('labels', {}).get('service_name')
        key = (service, j.get('queue')); stamp = parse_time(e.get('timestamp'))
        if key not in expected or key in latest or stamp is None:
            continue
        counters = ('failed', 'pending', 'oldestSeconds', 'held', 'expiredLeases', 'paymentReviews',
                    'expectedWaiting', 'expectedWaitingOldestSeconds', 'expectedWaitingOverdue')
        values = {k: j[k] for k in counters if (type(j.get(k)) is int and j[k] >= 0)
                  or (k == 'expectedWaitingOverdue' and type(j.get(k)) is bool)}
        fresh = 0 <= (now - stamp).total_seconds() <= 1800
        required = {'failed', 'pending', 'oldestSeconds'}
        if key[1] in ('home_financial', 'home_events'):
            required.update(counters)
        healthy = (fresh and e.get('severity') == 'INFO'
                   and all(k in values for k in required)
                   and not any(values.get(k, 0) for k in ('failed', 'held', 'expiredLeases', 'paymentReviews', 'expectedWaitingOverdue'))
                   and values['oldestSeconds'] < 600)
        latest[key] = {'service': service, 'queue': key[1], 'time': stamp.isoformat(),
                       'state': 'healthy' if healthy else 'attention_required', **values}
    queues = [latest.get(key, {'service': key[0], 'queue': key[1], 'state': 'missing_evidence'}) for key in sorted(expected)]
    return {'environment': environment, 'checkedAt': now.isoformat(), 'lookbackHours': hours, 'readOnly': True,
            'jobs': jobs, 'queues': queues, 'hiringAsyncBillingEnabled': billing_enabled,
            'passed': all(j['state'] == 'healthy' for j in jobs) and all(q['state'] == 'healthy' for q in queues)}


def dashboard():
    """One IAM-protected view over existing logs; no new metrics, polling or alert policies."""
    def logs(title, query, projects=(PROJECT,)):
        return {'title': title, 'logsPanel': {'filter': query, 'resourceNames': ['projects/' + p for p in projects]}}
    active = 'resource.type="cloud_run_revision" AND resource.labels.service_name=("cookcredit-home" OR "cookcredit-hiring")'
    jobs = 'resource.type="cloud_scheduler_job" AND resource.labels.job_id=~"^cc-(hiring|home)-"'
    return {'displayName': DASHBOARD_TITLE, 'labels': {'cookcredit_operations': ''}, 'gridLayout': {'columns': '2', 'widgets': [
        {'title': 'Read failures with recovery evidence', 'text': {'format': 'MARKDOWN', 'content':
            'Keep alerts and retries enabled. Compare each failed Scheduler attempt with its next successful attempt and the latest queue counters below. '
            'HTTP 200 confirms an invocation, not email delivery or settlement. '
            'Use `python deploy/platform_monitoring.py --environment production --include-shared` for the bounded recovery review. '
            'Never replay payments or messages without checking durable state.'}},
        {'title': 'Legacy retention requires a data decision', 'text': {'format': 'MARKDOWN', 'content':
            '`biometric-retention-sweep` targets the legacy database. When its activation policy is `NEVER`, cleanup is blocked. '
            'Do not mute its errors, delete data, restart the database or retire shared assessment storage to make the view green. '
            'Review dependencies, actual records, retention obligations and recovery before an approved retirement.'}},
        logs('Production server and delivery errors', active + ' AND (severity>=ERROR OR httpRequest.status>=500)'),
        logs('Home rejected requests: safe reason and support reference', 'resource.type="cloud_run_revision" AND resource.labels.service_name="cookcredit-home" AND jsonPayload.event="home_request_rejected"'),
        logs('Failed background attempts', jobs + ' AND severity>=ERROR'),
        logs('Successful background attempts: compare job and timestamp', jobs + ' AND jsonPayload."@type"="' + FINISHED + '" AND httpRequest.status=200'),
        logs('Latest durable queue counters', active + ' AND jsonPayload.event="queue_health"'),
        logs('Legacy and shared assessment cleanup', '(resource.type="cloud_scheduler_job" AND resource.labels.job_id=("biometric-retention-sweep" OR "firebase-schedule-purgeExpiredCookCreditSkillData-us-central1"))', (PROJECT, SHARED_PROJECT)),
    ]}}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--environment', required=True, choices=('staging', 'production'))
    parser.add_argument('--hours', type=int, default=24, choices=range(2, 49))
    parser.add_argument('--include-shared', action='store_true')
    args = parser.parse_args()
    try:
        from hiring_staging import client, api
        result = review(client(), api, args.environment, hours=args.hours, include_shared=args.include_shared)
    except Exception:
        result = {'passed': False, 'unavailable': True, 'readOnly': True}
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['passed'] else 1)
