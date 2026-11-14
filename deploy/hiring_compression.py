"""Pure deployment plans for the optional, on-demand Hiring playback job.

Review the returned configuration before applying it with the existing release
tooling. No credentials, queue, scheduler or service is created on import.
"""
import copy
import re

PROJECT = 'cookcredit-scoring'
REGION = 'us-central1'
ENVIRONMENT_KEYS = frozenset(('CLOUD_SQL_CONNECTION', 'DB_USER', 'DB_PASS', 'DB_NAME',
    'DB_SOCKET_DIR', 'DATABASE_URL', 'FIREBASE_USE_ADC', 'FIREBASE_PROJECT_ID', 'FIREBASE_STORAGE_BUCKET'))


def job_name(environment):
    if environment not in ('staging', 'production'):
        raise ValueError('Unknown environment')
    return f'projects/{PROJECT}/locations/{REGION}/jobs/cc-hiring-' + ('stg-' if environment == 'staging' else '') + 'compression'


def desired_job(service, environment, image, commit):
    expected = 'cookcredit-hiring' + ('-staging' if environment == 'staging' else '')
    if (not service['name'].endswith('/services/' + expected)
            or not re.fullmatch(r'us-central1-docker.pkg.dev/cookcredit-scoring/cookcredit-hiring/compression@sha256:[a-f0-9]{64}', image)
            or not re.fullmatch('[a-f0-9]{40}', commit)):
        raise ValueError('Unexpected service, worker image or source')
    source = service['template']
    container = source['containers'][0]
    env = [copy.deepcopy(e) for e in container.get('env', []) if e['name'] in ENVIRONMENT_KEYS]
    assert any(e['name'] == 'FIREBASE_STORAGE_BUCKET' for e in env)
    assert any(e['name'] in ('DB_PASS', 'DATABASE_URL') for e in env)
    env += [{'name': 'RELEASE_COMMIT', 'value': commit}, {'name': 'DB_POOL_SIZE', 'value': '1'},
            {'name': 'DB_MAX_OVERFLOW', 'value': '0'}]
    # Reuse the environment's identity and Cloud SQL connection. Do not copy
    # Stripe, SMTP, integration secrets, API listeners or unrelated volumes.
    volumes = [copy.deepcopy(v) for v in source.get('volumes', []) if 'cloudSqlInstance' in v]
    mounts = [copy.deepcopy(m) for m in container.get('volumeMounts', [])
              if m['name'] in {v['name'] for v in volumes}]
    return {'name': job_name(environment), 'labels': {'product': 'cookcredit-hiring', 'environment': environment},
        'template': {'parallelism': 1, 'taskCount': 1, 'template': {
            'serviceAccount': source['serviceAccount'], 'timeout': '900s', 'maxRetries': 0,
            'executionEnvironment': 'EXECUTION_ENVIRONMENT_GEN2',
            'volumes': volumes, 'containers': [{'name': 'compression', 'image': image,
                'env': env, 'volumeMounts': mounts, 'resources': {'limits': {'cpu': '1', 'memory': '1Gi'}}}],
            **({'vpcAccess': copy.deepcopy(source['vpcAccess'])} if source.get('vpcAccess') else {})}}}


def derivative_lifecycle(bucket):
    lifecycle = copy.deepcopy(bucket.get('lifecycle', {'rule': []}))
    rule = {'action': {'type': 'Delete'}, 'condition': {
        'daysSinceCustomTime': 30, 'matchesPrefix': ['hiring-playback/']}}
    if rule not in lifecycle['rule']:
        lifecycle['rule'].append(rule)
    return lifecycle
