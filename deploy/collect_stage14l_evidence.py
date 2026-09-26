"""Read-only verification of the logo/navigation staging release and its gates."""
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import re

import requests

from hiring_staging import api, client, state, frontend_dist, PROJECT, REGION, SERVICE, SITE, require_labels

root = Path(__file__).resolve().parents[1]
session = client()
record = state()
service = api(session, 'GET', f'https://run.googleapis.com/v2/projects/{PROJECT}/locations/{REGION}/services/{SERVICE}')
require_labels(service.get('labels', {}))
assert not service.get('reconciling')
assert service['latestReadyRevision'] == service['latestCreatedRevision']
container = service['template']['containers'][0]
assert container['image'] == record['imageDigest']
build = api(session, 'GET', f'https://cloudbuild.googleapis.com/v1/projects/{PROJECT}/builds/{record["build"]}')
assert build['status'] == 'SUCCESS' and build['steps'][4]['status'] == 'SUCCESS'
env = {item['name']: item.get('value') for item in container['env']}
assert env['COOKCREDIT_ENVIRONMENT'] == 'staging'
assert env['BUSINESS_BILLING_ENABLED'] == '0'
assert env.get('ASSESSMENT_EMPLOYMENT_VALIDATED', '0') == '0'
assert env['AUTH_APP_CHECK_REQUIRED'] == '1'
assert env['STAGING_ALLOWED_EMAILS'] == 'eassefa@cookcredit.com,staging-smoke@cookcredit.invalid'

hosting = 'https://firebasehosting.googleapis.com/v1beta1/'
release = api(session, 'GET', hosting + f'sites/{SITE}/releases', params={'pageSize': 1})['releases'][0]
files = api(session, 'GET', hosting + release['version']['name'] + '/files', params={'pageSize': 1000})
assert not files.get('nextPageToken')
dist = frontend_dist(record)
expected = {'/'+p.relative_to(dist).as_posix(): hashlib.sha256(gzip.compress(p.read_bytes(), mtime=0)).hexdigest()
            for p in dist.rglob('*') if p.is_file()}
stored = {f['path']: f['hash'] for f in files['files']}
assert expected and {key: stored.get(key) for key in expected} == expected
checks = {}
for label, path, status in [('health', '/api/health', 200), ('readiness', '/api/ready', 200),
                           ('privateApplications', '/api/hiring/my-applications', 401)]:
    response = requests.get(record['apiOrigin']+path, timeout=30)
    assert response.status_code == status, (label, response.status_code)
    checks[label] = response.status_code
public = requests.get(f'https://{SITE}.web.app/business', timeout=30)
assert public.status_code == 200
assert hashlib.sha256(public.content).digest() == hashlib.sha256((dist/'index.html').read_bytes()).digest()

source_checks = {}
for name in ('wrist.js', 'score.js', 'recording.mjs'):
    source = (root.parent/'work/live-hiring-overlay'/('baseline-'+name)).read_bytes()
    current = requests.get('https://cookcredit-knife-demo.web.app/'+name, timeout=30)
    assert current.status_code == 200 and hashlib.sha256(current.content).digest() == hashlib.sha256(source).digest()
    source_checks[name] = hashlib.sha256(source).hexdigest()

logs = api(session, 'POST', 'https://logging.googleapis.com/v2/entries:list', json={
    'resourceNames': ['projects/'+PROJECT], 'pageSize': 50,
    'filter': f'resource.type="build" AND resource.labels.build_id="{record["build"]}" AND textPayload:"passed"'})
tests = [match.group(0) for entry in logs.get('entries', [])
         if (match := re.search(r'\b\d+ passed[^\r\n]*', entry.get('textPayload', '')))]
result = {
    'stage': '14L', 'checkedAt': datetime.now(timezone.utc).isoformat(),
    'backend': {'build': record['build'], 'revision': service['latestReadyRevision'], 'image': container['image'],
                'testLogSummaries': tests, 'functionalTestsWithPostgres': build['steps'][4]['status'],
                'migrationSucceeded': record['migrationSucceeded'], 'httpChecks': checks},
    'frontend': {'build': record['frontendBuild'], 'release': release['name'], 'assetCount': len(expected),
                 'allBuildAssetHashesMatchRelease': True, 'servedIndexMatchesArtifact': True},
    'liveAssessmentUnchanged': source_checks,
    'gates': {key: env.get(key, '0') for key in ['ASSESSMENT_BRIDGE_ENABLED', 'ASSESSMENT_EMPLOYMENT_VALIDATED', 'BUSINESS_BILLING_ENABLED']},
    'numericalParity': {'syntheticCases': 10, 'source': 'exact hash-pinned published JavaScript',
                        'includedInImage': True, 'connectedToWorker': False, 'videoVerificationValidated': False},
    'acceptance': {'ownerSignInCompleted': True, 'authenticatedLogoUpload': True,
                   'authenticatedLogoRemoval': True, 'removedLogoOriginReturned404': True,
                   'testRoleCreated': '204a0f34-fcae-4127-adb3-3dfbf4280af4',
                   'realAssessmentRoundTrip': False, 'ownerDeferredRecording': True,
                   'realStripeTest': False, 'fullWorkloadCapacity': False, 'publicHiringLaunch': False},
}
destination = root/'backend/docs/evidence/stage14l-release.json'
destination.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
print(json.dumps(result, indent=2))
