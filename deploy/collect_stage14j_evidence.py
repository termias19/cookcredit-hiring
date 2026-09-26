"""Read-only cloud evidence; reconcile the local release ledger from asset hashes."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import gzip
import hashlib
import requests
from hiring_staging import api, client, state, save, frontend_dist, PROJECT, REGION, SERVICE, SITE, require_labels

root = Path(__file__).resolve().parents[1]
record = state()
session = client()
service = api(session, 'GET', f'https://run.googleapis.com/v2/projects/{PROJECT}/locations/{REGION}/services/{SERVICE}')
require_labels(service.get('labels', {}))
container = service['template']['containers'][0]
assert container['image'] == record['imageDigest']
env = {item['name']: item.get('value') for item in container['env'] if 'value' in item}
build = api(session, 'GET', f'https://cloudbuild.googleapis.com/v1/projects/{PROJECT}/builds/{record["build"]}')
frontend = api(session, 'GET', f'https://cloudbuild.googleapis.com/v1/projects/{PROJECT}/builds/{record["frontendBuild"]}')
assert build['status'] == frontend['status'] == 'SUCCESS'
assert build['steps'][4]['status'] == 'SUCCESS'
hosting_api = 'https://firebasehosting.googleapis.com/v1beta1/'
release = api(session, 'GET', hosting_api+f'sites/{SITE}/releases', params={'pageSize': 1})['releases'][0]
listing = api(session, 'GET', hosting_api+release['version']['name']+'/files', params={'pageSize': 1000})
dist = frontend_dist(record)
expected = {'/'+p.relative_to(dist).as_posix(): hashlib.sha256(gzip.compress(p.read_bytes(), mtime=0)).hexdigest()
            for p in dist.rglob('*') if p.is_file()}
stored = {f['path']: f['hash'] for f in listing['files']}
managed = {'/__/firebase/init.json', '/__/firebase/init.js'}
assert expected and set(stored)-set(expected) <= managed
assert {key: stored.get(key) for key in expected} == expected
assert not listing.get('nextPageToken')
record.update(hostingRelease=release['name'], hostingVersion=release['version']['name'],
              hostedFrontendBuild=record['frontendBuild'])
save(record)
logs = api(session, 'POST', 'https://logging.googleapis.com/v2/entries:list', json={
    'resourceNames': ['projects/'+PROJECT], 'pageSize': 50,
    'filter': f'resource.type="build" AND resource.labels.build_id="{record["build"]}" AND textPayload:"passed"'})
test_summaries = []
for entry in logs.get('entries', []):
    match = re.search(r'\b\d+ passed[^\r\n]*', entry.get('textPayload', ''))
    if match:
        test_summaries.append(match.group(0).strip('= '))
origin = record['apiOrigin']
health = requests.get(origin+'/api/health', timeout=45)
ready = requests.get(origin+'/api/ready', timeout=45)
assert health.status_code == ready.status_code == 200
preflight = requests.options(origin+'/api/hiring/assessment-sessions/123e4567-e89b-42d3-a456-426614174000/complete',
    headers={'Origin': 'https://cookcredit-knife-demo.web.app', 'Access-Control-Request-Method': 'POST',
             'Access-Control-Request-Headers': 'authorization,content-type,x-firebase-appcheck'}, timeout=30)
assert preflight.status_code in (200, 204)
assert preflight.headers.get('Access-Control-Allow-Origin') == 'https://cookcredit-knife-demo.web.app'
assert 'X-Firebase-AppCheck' in preflight.headers.get('Access-Control-Allow-Headers', '')
manifest = json.loads((root.parent/'work/live-hiring-overlay/manifest.json').read_text())
assert manifest.get('publicHttpVerified')
result = {
    'stage': '14J', 'checkedAt': datetime.now(timezone.utc).isoformat(),
    'backend': {'build': record['build'], 'image': container['image'], 'revision': service['latestReadyRevision'],
                'testLogSummaries': test_summaries, 'functionalTestStepPassed': True,
                'migrationSucceeded': record['migrationSucceeded'],
                'healthStatus': health.status_code, 'readinessStatus': ready.status_code,
                'assessmentAppCheckCors': True},
    'frontend': {'build': record['frontendBuild'], 'release': record['hostingRelease'],
                 'url': record['frontendUrl'], 'buildStatus': frontend['status'],
                 'policyLinksDeployed': True, 'allBuildAssetHashesMatchRelease': True,
                 'assetCount': len(expected), 'firebaseManagedAssetCount': len(set(stored)-set(expected))},
    'liveAssessment': {'sourceVersion': manifest['baseVersion'], 'overlayRelease': manifest['release'],
                       'url': 'https://cookcredit-knife-demo.web.app/hiring/',
                       'originalPublicAssetsUnchanged': len(manifest['originalPaths']),
                       'protectedAssets': manifest['protected'], 'bridgeBehaviorTests': 13,
                       'publicHttpVerified': True, 'fullRoundTripVerified': False},
    'gates': {name: env.get(name, '0') for name in ('ASSESSMENT_BRIDGE_ENABLED', 'ENGINE_APPLICANT_IMPORT_ENABLED',
                 'BUSINESS_BILLING_ENABLED', 'ASSESSMENT_EMPLOYMENT_VALIDATED')},
    'invitedAccountsOnly': bool(env.get('STAGING_ALLOWED_EMAILS')),
    'browserChecks': {'method': 'CUA screenshots and rendered DOM',
                      'desktopLoginWidth': 945, 'mobileSignupWidth': 390,
                      'mobileForgotWidth': 390, 'mobileAssessmentWidth': 390,
                      'horizontalOverflowObserved': False,
                      'signedOutAssessmentCameraStartDisabled': True,
                      'ownerSignInCompleted': False, 'physicalDeviceCameraTestCompleted': False},
    'email': {'previewHasPrivacyAndTerms': True, 'customTemplateDeliveryEnabled': False,
              'nativeFirebaseDeliveryUnchanged': True},
    'newLoadTestingRun': False,
    'blockers': ['Published wrist-motion metrics differ from hiring product-quality scoring contract',
                 'Actual account-to-recording-to-employer round trip not completed',
                 'Custom email footer/logo delivery needs an active email provider',
                 'Payment test key deferred by owner; payment and load tests follow functional acceptance'],
}
out = root/'backend/docs/evidence/stage-14j-live-connection.json'
out.write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps(result, indent=2))
