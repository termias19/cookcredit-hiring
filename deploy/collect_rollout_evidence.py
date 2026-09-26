"""Export only named probe reports and public deployment identifiers."""
import json
import re
import hashlib
import requests
from pathlib import Path
from datetime import datetime, timezone
from hiring_staging import client, api, state, PROJECT, SERVICE, REGION
from hiring_recovery import read as recovery_state

def main():
    session = client()
    record = state()
    report = {'checkedAt': datetime.now(timezone.utc).isoformat(), 'stage': '14I',
        'email': {'recipientDeliveryConfirmedByOwner': True,
                  'nativeBrowserResetRequestSucceeded': True,
                  'passwordChangeCompleted': False, 'newAccountVerificationCompleted': False,
                  'acceptedBrand': 'CookCredit', 'emailHeaderLogoInstalled': False,
                  'senderAvatarInstalled': False, 'dmarcPolicy': 'none', 'bimiRecordPresent': False,
                  'customEmailLogoTemplatePrepared': True,
                  'customEmailLogoTemplateDeployed': False,
                  'pngLogoPublished': False, 'bimiAssetCertificateValidated': False},
        'sharedAuthProject': record['firebaseConfig']['projectId'], 'stagingWebApp': record['firebaseApp'],
        'frontendBuild': record['frontendBuild'], 'hostedFrontendBuild': record.get('hostedFrontendBuild'),
        'hostingRelease': record['hostingRelease'],
        'backendBuild': record['build'], 'image': record.get('imageDigest'), 'recovery': recovery_state()}
    service = api(session, 'GET', f'https://run.googleapis.com/v2/projects/{PROJECT}/locations/{REGION}/services/{SERVICE}')
    report['apiReadyRevision'] = service.get('latestReadyRevision')
    container = service['template']['containers'][0]
    report['deployedImage'] = container['image']
    build = api(session, 'GET', f'https://cloudbuild.googleapis.com/v1/projects/{PROJECT}/builds/{record["build"]}')
    report['backendBuildStatus'] = build['status']
    frontend_build = api(session, 'GET', f'https://cloudbuild.googleapis.com/v1/projects/{PROJECT}/builds/{record["frontendBuild"]}')
    report['frontendBuildStatus'] = frontend_build['status']
    entries = api(session, 'POST', 'https://logging.googleapis.com/v2/entries:list', json={
        'resourceNames': ['projects/'+PROJECT],
        'filter': f'resource.type="build" AND resource.labels.build_id="{record["build"]}" '
                  'AND (textPayload:"passed" OR textPayload:"COOKCREDIT_LOAD_REPORT=")',
        'pageSize': 50, 'orderBy': 'timestamp desc'}).get('entries', [])
    for entry in entries:
        line = entry.get('textPayload', '')
        if 'COOKCREDIT_LOAD_REPORT=' in line:
            report['disposableLoad'] = json.loads(line.split('COOKCREDIT_LOAD_REPORT=', 1)[1])
        elif match := re.search(r'(\d+) passed in ([\d.]+)s', line):
            report['backendTests'] = {'passed': int(match[1]), 'seconds': float(match[2])}
    logo = requests.get('https://cookcredit-hiring-staging.web.app/cookcredit-mark-orange.png', timeout=20)
    source_logo = Path(__file__).resolve().parents[1] / 'frontend/public/cookcredit-mark-orange.png'
    report['email']['pngLogoPublished'] = (logo.status_code == 200
        and logo.headers.get('Content-Type', '').startswith('image/png')
        and hashlib.sha256(logo.content).digest() == hashlib.sha256(source_logo.read_bytes()).digest())
    allowed = {'FIREBASE_PROJECT_ID', 'FIREBASE_STORAGE_BUCKET', 'AUTH_EMAILS_ENABLED',
               'ASSESSMENT_BRIDGE_ENABLED', 'BUSINESS_BILLING_ENABLED', 'ASSESSMENT_PUBLIC_URL'}
    report['runtime'] = {v['name']: v['value'] for v in container['env'] if v['name'] in allowed and 'value' in v}
    for job, prefix in [('cc-hiring-stg-recovery', 'COOKCREDIT_RECOVERY='),
                        ('cc-hiring-stg-sustained', 'COOKCREDIT_SUSTAINED=')]:
        entries = api(session, 'POST', 'https://logging.googleapis.com/v2/entries:list', json={
            'resourceNames': ['projects/'+PROJECT],
            'filter': f'resource.type="cloud_run_job" AND resource.labels.job_name="{job}" AND textPayload:"{prefix}"',
            'pageSize': 1, 'orderBy': 'timestamp desc'}).get('entries', [])
        if entries:
            report[job] = json.loads(entries[0]['textPayload'].split(prefix, 1)[1])
    destination = Path(__file__).resolve().parents[1] / 'backend/docs/evidence/stage-14i-rollout.json'
    destination.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))

if __name__ == '__main__': main()
