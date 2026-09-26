"""Capture only explicit synthetic test reports; never dump credentials or users."""
import json
from pathlib import Path
import re
import subprocess
from datetime import datetime, timezone
import hiring_staging as deployment


def logs(filter_text, limit=5):
    result = subprocess.run(['gcloud.cmd', 'logging', 'read', filter_text,
        '--project='+deployment.PROJECT, '--account='+deployment.ACCOUNT,
        '--limit='+str(limit), '--freshness=6h', '--format=json'],
        capture_output=True, text=True, check=True, timeout=90)
    return json.loads(result.stdout)


def report(job, marker):
    entries = logs(f'resource.type="cloud_run_job" AND resource.labels.job_name="{job}" AND textPayload:"{marker}"', 1)
    if len(entries) != 1:
        raise RuntimeError('Expected a single successful synthetic test report')
    return json.loads(entries[0]['textPayload'].split(marker, 1)[1])


state = deployment.state()
if not state.get('probeSucceeded') or not state.get('webhookProbeSucceeded'):
    raise RuntimeError('Both cloud jobs must complete successfully before capturing success evidence')
probe = report('cc-hiring-stg-probe', 'COOKCREDIT_STAGING_PROBE=')
hook = report('cc-hiring-stg-hookprobe', 'COOKCREDIT_WEBHOOK_DRILL=')
if any(row['revision'] != state['apiReadyRevision'].rsplit('/', 1)[-1] for row in probe['metadataProbes']):
    raise RuntimeError('Probe did not test the currently recorded ready revision')
entries = logs('resource.type="build" AND resource.labels.build_id="'+state['build']+'" AND (textPayload:"passed in" OR textPayload:"COOKCREDIT_LOAD_REPORT=")')
unit_count = None
ephemeral = None
for entry in entries:
    line = entry.get('textPayload', '')
    match = re.search(r'(\d+) passed in', line)
    if match:
        unit_count = int(match.group(1))
    if 'COOKCREDIT_LOAD_REPORT=' in line:
        ephemeral = json.loads(line.split('COOKCREDIT_LOAD_REPORT=', 1)[1])
if unit_count is None or ephemeral is None:
    raise RuntimeError('Verification build evidence is incomplete')
queue = logs('resource.type="cloud_tasks_queue" AND jsonPayload.task="'+probe['queueProbeTask']+'" AND jsonPayload.attemptResponseLog.status="OK"', 1)
if not queue:
    raise RuntimeError('Queue delivery success was not found')
record = {'capturedAt': datetime.now(timezone.utc).isoformat(),
    'release': {key: state[key] for key in ('project', 'region', 'build', 'imageDigest', 'apiReadyRevision',
        'frontendBuild', 'hostingRelease', 'frontendUrl')},
    'backendTestsPassed': unit_count, 'ephemeralBuildLoad': ephemeral, 'cloudProbe': probe,
    'webhookDrill': hook, 'queueDelivery': queue[0]['jsonPayload']['attemptResponseLog'],
    'firstBurstFailure': {'revision': 'cookcredit-hiring-staging-00001-nkv', 'platform500s': 6,
        'reason': 'No available instance during cold scaling',
        'change': 'One warm instance and concurrency 16, retaining maximum three per revision'},
    'notVerified': ['Professional email/inbox and signup journey', 'Real Stripe subscription journey',
        'Exact live assessment capture/scoring/handoff', 'Customer ATS completion-to-stage-transition',
        'Sustained mixed-load capacity', 'Backup restore drill and operational alert delivery']}
destination = Path(__file__).resolve().parents[1]/'backend/docs/evidence/stage-14g-cloud.json'
destination.parent.mkdir(exist_ok=True)
destination.write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8')
print('Captured sanitized cloud verification evidence: '+str(destination))
