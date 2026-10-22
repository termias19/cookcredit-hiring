"""Read-only release gate: public search policy, API readiness and recent error logs.

Run after a candidate release and again after promotion. It never signs in, sends
mail, creates data, charges cards, or follows an applicant invitation.
"""
import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sys
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from services.public_site_health import check_public_site

API = {
    'production': 'https://cookcredit-hiring-915097816203.us-central1.run.app',
    'staging': 'https://cookcredit-hiring-staging-915097816203.us-central1.run.app',
}


def run(environment, *, commit=None, logs=False, lookback=15):
    result = {'environment': environment, 'checkedAt': datetime.now(timezone.utc).isoformat(),
              'publicSite': check_public_site(environment), 'api': [], 'recentErrors': None}
    ok = result['publicSite']
    for path, expected in [('/api/ready', 200), ('/api/business/team', 401),
                           ('/api/business/activity', 401), ('/api/business/candidates', 401)]:
        try:
            r = requests.get(API[environment] + path, timeout=(3, 15), allow_redirects=False)
            passed = r.status_code == expected
            if commit:
                passed = passed and r.headers.get('X-Release-Commit') == commit
            if path == '/api/ready':
                passed = passed and r.json().get('status') == 'ready'
            result['api'].append({'path': path, 'status': r.status_code, 'passed': bool(passed)})
            ok = ok and passed
        except Exception:
            result['api'].append({'path': path, 'passed': False})
            ok = False
    if logs:
        from hiring_staging import client, api
        service = 'cookcredit-hiring' + ('-staging' if environment == 'staging' else '')
        since = (datetime.now(timezone.utc) - timedelta(minutes=lookback)).isoformat().replace('+00:00', 'Z')
        query = ('resource.type="cloud_run_revision" AND resource.labels.service_name="' + service
                 + '" AND timestamp>="' + since + '" AND (severity>=ERROR OR httpRequest.status>=500)')
        if commit:
            # Include platform errors without jsonPayload as well as this release's events.
            query += ' AND (jsonPayload.commit="' + commit + '" OR NOT jsonPayload.commit:*)'
        try:
            session = client()
            data = api(session, 'POST', 'https://logging.googleapis.com/v2/entries:list',
                       json={'resourceNames': ['projects/cookcredit-scoring'], 'filter': query,
                             'pageSize': 100, 'orderBy': 'timestamp desc'})
            entries = data.get('entries', [])
            groups = Counter(e.get('jsonPayload', {}).get('event', 'platform_or_unstructured') for e in entries)
            result['recentErrors'] = {'count': len(entries), 'truncated': bool(data.get('nextPageToken')),
                                      'groups': dict(groups), 'lookbackMinutes': lookback}
            ok = ok and not entries and not data.get('nextPageToken')
            # The latest completed run of each existing worker must be successful.
            # A prior transport failure followed by success is recorded as recovered.
            prefix = 'cc-hiring-' + ('stg-' if environment == 'staging' else '')
            names = [prefix + suffix for suffix in ('emails', 'webhooks', 'expiry', 'dispatch')]
            jobs = api(session, 'GET', 'https://cloudscheduler.googleapis.com/v1/projects/'
                       'cookcredit-scoring/locations/us-central1/jobs')
            enabled = {j['name'].rsplit('/', 1)[-1] for j in jobs.get('jobs', []) if j.get('state') == 'ENABLED'}
            worker_query = ('resource.type="cloud_scheduler_job" AND timestamp>="' + since
                            + '" AND jsonPayload."@type"="type.googleapis.com/google.cloud.scheduler.logging.AttemptFinished"'
                            + ' AND resource.labels.job_id=(' + ' OR '.join('"' + n + '"' for n in names) + ')')
            worker_logs = api(session, 'POST', 'https://logging.googleapis.com/v2/entries:list',
                              json={'resourceNames': ['projects/cookcredit-scoring'], 'filter': worker_query,
                                    'pageSize': 100, 'orderBy': 'timestamp desc'})
            latest = {};failure_counts = Counter()
            for entry in worker_logs.get('entries', []):
                name = entry.get('resource', {}).get('labels', {}).get('job_id')
                status = entry.get('httpRequest', {}).get('status', 0)
                if name not in latest:latest[name] = status
                if status != 200:failure_counts[name] += 1
            result['workers'] = [{'job': name, 'enabled': name in enabled,
                                  'lastStatus': latest.get(name), 'failuresInWindow': failure_counts[name]}
                                 for name in names]
            ok = ok and all(name in enabled and latest.get(name) == 200 for name in names)
            if worker_logs.get('nextPageToken'):
                result['workersTruncated'] = True
                ok = False
        except Exception:
            result['recentErrors'] = {'unavailable': True}
            ok = False  # Missing log access is never a passing error review.
    result['passed'] = bool(ok)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--environment', choices=API, required=True)
    parser.add_argument('--commit', type=lambda value: value if re.fullmatch(r'[a-f0-9]{40}', value) else parser.error('commit must be 40 lowercase hex characters'))
    parser.add_argument('--logs', action='store_true')
    parser.add_argument('--lookback-minutes', type=int, choices=range(5, 61), default=15)
    args = parser.parse_args()
    result = run(args.environment, commit=args.commit, logs=args.logs, lookback=args.lookback_minutes)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['passed'] else 1)
