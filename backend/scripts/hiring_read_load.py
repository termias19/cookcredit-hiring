"""Bounded metadata load probe for isolated staging; never accepts secrets in argv.

Set COOKCREDIT_LOAD_TOKEN to a cc_test_ partner key, or a Firebase ID token for a
synthetic employer (applicants scenario). Production and redirects are refused.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import time
from urllib.parse import urlsplit
import uuid
from threading import Lock
import requests


def validated_origin(value):
    u = urlsplit(value)
    local = u.hostname in ('localhost', '127.0.0.1')
    if (u.username or u.password or u.query or u.fragment or u.path not in ('', '/')
            or not u.hostname or (u.scheme != 'https' and not (local and u.scheme == 'http'))):
        raise ValueError('Use an HTTPS staging origin or an explicit localhost origin')
    return value.rstrip('/'), local


def validate_health(data, local):
    if data.get('app') != 'CookCredit' or data.get('database') is not True:
        raise ValueError('The target is not a healthy CookCredit API')
    allowed = {'staging', 'development'} if local else {'staging'}
    if data.get('environment') not in allowed:
        raise ValueError('Load testing production or an unmarked environment is forbidden')


def assessment_request_body(run_id, identity):
    """Exercise the published hiring contract, with synthetic test identities only."""
    return {'externalJobId': run_id, 'jobTitle': 'Synthetic load test - not a vacancy',
            'externalCandidateId': f'{run_id}-{identity}', 'candidateEmail': f'{run_id}-{identity}@example.test',
            'environment': 'test', 'attemptLimit': 3,
            'assessmentProfile': 'wrist_motion', 'assessmentProfileVersion': 'knife-motion-v1',
            'assessmentCriteria': {'profileVersion': 'knife-motion-v1', 'minimumRhythm': 75}}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base-url', required=True)
    p.add_argument('--scenario', choices=['applicants', 'requests', 'create', 'retry'], default='requests')
    p.add_argument('--role-id')
    p.add_argument('--requests', type=int, default=100)
    p.add_argument('--workers', type=int, default=5)
    p.add_argument('--rps', type=float, default=5)
    p.add_argument('--timeout', type=float, default=20)
    p.add_argument('--output', required=True)
    args = p.parse_args()
    try:
        origin, local = validated_origin(args.base_url)
        if not (1 <= args.requests <= 20000 and 1 <= args.workers <= 100 and 0 < args.rps <= 200 and 0 < args.timeout <= 120):
            raise ValueError('Bounds: 1-20000 requests, 1-100 workers, 0-200 RPS, 0-120 seconds timeout')
        token = os.environ.get('COOKCREDIT_LOAD_TOKEN', '')
        if not token:
            raise ValueError('Set COOKCREDIT_LOAD_TOKEN in the environment')
        if args.scenario != 'applicants' and not token.startswith('cc_test_'):
            raise ValueError('Partner scenarios require a test key, never a live key')
        if args.scenario == 'applicants':
            uuid.UUID(args.role_id or '')
        response = requests.get(origin + '/api/health', timeout=args.timeout, allow_redirects=False)
        response.raise_for_status()
        health = response.json()
        validate_health(health, local)
    except (ValueError, requests.RequestException) as exc:
        p.error(str(exc))
    run_id = 'load-' + uuid.uuid4().hex
    headers = {'Authorization': 'Bearer ' + token}
    active = 0
    peak_active = 0
    active_lock = Lock()
    start = time.perf_counter()
    started_at = datetime.now(timezone.utc).isoformat()

    def one(index):
        nonlocal active, peak_active
        delay = start + index / args.rps - time.perf_counter()
        if delay > 0:
            time.sleep(delay)
        begin = time.perf_counter()
        identity = 0 if args.scenario == 'retry' else index
        body = assessment_request_body(run_id, identity)
        resource_id = None
        with active_lock:
            active += 1
            peak_active = max(peak_active, active)
        try:
            if args.scenario in ('create', 'retry'):
                response = requests.post(origin + '/api/partner/v1/assessment-requests', json=body,
                    headers={**headers, 'Idempotency-Key': f'{run_id}-{identity}'}, timeout=args.timeout, allow_redirects=False)
            else:
                path = (f'/api/hiring/roles/{args.role_id}/applications?limit=40' if args.scenario == 'applicants'
                        else '/api/partner/v1/assessment-requests')
                response = requests.get(origin + path, headers=headers, timeout=args.timeout, allow_redirects=False)
            status = response.status_code
            if 200 <= status < 300:
                data = response.json()
                if args.scenario in ('create', 'retry'):
                    resource_id = data.get('data', {}).get('id')
                    if not resource_id or data['data'].get('environment') != 'test':
                        status = -2
        except (requests.RequestException, ValueError):
            status = 0
        finally:
            with active_lock:
                active -= 1
        return status, (time.perf_counter() - begin) * 1000, resource_id

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(one, range(args.requests)))
    wall = time.perf_counter() - start
    timings = sorted(row[1] for row in results)
    success = sum(200 <= row[0] < 300 for row in results)
    identities = {row[2] for row in results if row[2]}
    identity_ok = (len(identities) == 1 if args.scenario == 'retry' else
                   len(identities) == args.requests if args.scenario == 'create' else True)
    report = {'startedAt': started_at, 'target': origin, 'environment': health['environment'],
              'revision': health.get('revision'), 'runId': run_id, 'scenario': args.scenario,
              'requests': len(results), 'workers': args.workers, 'peakInflight': peak_active, 'targetRps': args.rps,
              'achievedRps': round(len(results) / wall, 2), 'statusCounts': dict(Counter(str(row[0]) for row in results)),
              'success': success, 'errors': len(results) - success, 'identityChecksPassed': identity_ok,
              'latencyMs': {name: round(timings[min(len(timings)-1, math.ceil(len(timings)*q)-1)], 2)
                            for name, q in [('p50', .5), ('p95', .95), ('p99', .99)]},
              'scope': 'Metadata API only. Does not prove upload, scoring, email or payment capacity.'}
    Path(args.output).write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    if success != args.requests or not identity_ok:
        raise SystemExit(1)


if __name__ == '__main__':
    main()

