"""CookCredit hiring staging only. No live resource defaults; no secret output.

Uses the named corporate login and records non-secret resource identifiers under
workspace/work. Re-running reuses only resources bearing our ownership labels.
"""
import argparse
import base64
import json
import os
from pathlib import Path
import secrets
import subprocess
import requests
from urllib.parse import quote
from datetime import datetime, timezone
import tarfile
import yaml
import gzip
import hashlib
import time
from uuid import UUID

PROJECT = 'cookcredit-scoring'
NUMBER = '915097816203'
ACCOUNT = 'eassefa@cookcredit.com'
REGION = 'us-central1'
SERVICE = 'cookcredit-hiring-staging'
SQL = 'cookcredit-hiring-stg-db'
REDIS = 'cookcredit-hiring-stg-redis'
RUNTIME = 'cc-hiring-stg-runtime'
MIGRATOR = 'cc-hiring-stg-migrate'
WORKER = 'cc-hiring-stg-dispatch'
SITE = 'cookcredit-hiring-staging'
BUCKET = 'cookcredit-hiring-stg-media-'+NUMBER
QUEUE = 'cookcredit-hiring-stg-scoring'
LABELS = {'product': 'cookcredit-hiring', 'environment': 'staging'}
STATE_FILE = Path(__file__).resolve().parents[2] / 'work' / 'hiring-staging-state.json'


def client():
    result = subprocess.run(['gcloud.cmd' if os.name == 'nt' else 'gcloud', 'auth',
        'print-access-token', '--account='+ACCOUNT, '--project='+PROJECT],
        capture_output=True, text=True, check=True, timeout=90)
    session = requests.Session()
    session.headers.update(Authorization='Bearer '+result.stdout.strip(),
                          **{'x-goog-user-project': PROJECT})
    return session


def api(session, method, url, *, missing=False, **kwargs):
    response = session.request(method, url, timeout=45, **kwargs)
    if missing and response.status_code == 404:
        return None
    if not response.ok:
        # Never print request bodies, provider bodies or credential-bearing URLs.
        try:
            error = response.json().get('error', {})
        except ValueError:
            error = {}
        if (url.startswith('https://run.googleapis.com/') and method in ('POST', 'PATCH')) or url.endswith(':setIamPolicy'):
            # Run requests contain secret resource references, never secret values.
            print('Cloud configuration error: '+error.get('message', ''), flush=True)
        raise RuntimeError(f'{method} {url.split("?")[0]}: HTTP {response.status_code} ({error.get("status", "provider error")})')
    return response.json() if response.content else {}


class DeploymentState(dict):
    def __init__(self, values):
        super().__init__(values)
        self.baseline = json.loads(json.dumps(values))


def state():
    return DeploymentState(json.loads(STATE_FILE.read_text()) if STATE_FILE.exists()
                           else {'project': PROJECT, 'region': REGION})


def save(data):
    STATE_FILE.parent.mkdir(exist_ok=True)
    lock = STATE_FILE.with_name(STATE_FILE.name+'.lock')
    deadline = time.monotonic()+5
    while True:
        try:
            lock.mkdir()
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise RuntimeError('Deployment ledger is locked; inspect the active release before retrying')
            time.sleep(0.05)
    try:
        current = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
        baseline = data.baseline if isinstance(data, DeploymentState) else current
        missing = object()
        for key in set(baseline) | set(data):
            before, after = baseline.get(key, missing), data.get(key, missing)
            if before == after:
                continue
            latest = current.get(key, missing)
            if latest != before and latest != after:
                raise RuntimeError('Concurrent deployment changed ledger field: '+key)
            if after is missing:
                current.pop(key, None)
            else:
                current[key] = after
        if not STATE_FILE.exists():
            current = dict(data)
        temporary = STATE_FILE.with_name(STATE_FILE.name+'.tmp')
        temporary.write_text(json.dumps(current, indent=2))
        os.replace(temporary, STATE_FILE)
        if isinstance(data, DeploymentState):
            data.clear()
            data.update(current)
            data.baseline = json.loads(json.dumps(current))
    finally:
        lock.rmdir()


def require_labels(actual):
    if any(actual.get(k) != v for k, v in LABELS.items()):
        raise RuntimeError('Existing resource is not owned by this hiring staging deployment')


def secret_value(session, name, create=None):
    if not name.startswith('COOKCREDIT_HIRING_'):
        raise RuntimeError('Refusing a non-hiring secret')
    endpoint = f'https://secretmanager.googleapis.com/v1/projects/{PROJECT}/secrets/{name}'
    resource = api(session, 'GET', endpoint, missing=True)
    if resource is None:
        api(session, 'POST', endpoint.rsplit('/', 1)[0], params={'secretId': name},
            json={'replication': {'automatic': {}}, 'labels': LABELS})
    versions = api(session, 'GET', endpoint+'/versions', params={'filter': 'state:ENABLED', 'pageSize': 1})
    if versions.get('versions'):
        payload = api(session, 'GET', 'https://secretmanager.googleapis.com/v1/'+versions['versions'][0]['name']+':access')
        return base64.b64decode(payload['payload']['data']).decode()
    if create is None:
        raise RuntimeError('Required dedicated secret has no enabled version: '+name)
    value = create()
    api(session, 'POST', endpoint+':addVersion', json={'payload': {'data': base64.b64encode(value.encode()).decode()}})
    return value


def provision():
    session = client()
    record = state()
    # All values remain in memory or dedicated Secret Manager versions.
    admin_password = secret_value(session, 'COOKCREDIT_HIRING_STG_DB_ADMIN_PASS', lambda: secrets.token_urlsafe(48))
    for name in ('DB_RUNTIME_PASS', 'INTERNAL_SECRET', 'API_KEY_PEPPER', 'SESSION_SECRET'):
        secret_value(session, 'COOKCREDIT_HIRING_STG_'+name, lambda: secrets.token_urlsafe(48))
    secret_value(session, 'COOKCREDIT_HIRING_STG_WEBHOOK_ENCRYPTION_KEY',
                 lambda: base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())
    for name in (RUNTIME, MIGRATOR, WORKER):
        email = f'{name}@{PROJECT}.iam.gserviceaccount.com'
        endpoint = f'https://iam.googleapis.com/v1/projects/{PROJECT}/serviceAccounts/{email}'
        if api(session, 'GET', endpoint, missing=True) is None:
            api(session, 'POST', endpoint.rsplit('/', 1)[0], json={'accountId': name,
                'serviceAccount': {'displayName': 'CookCredit hiring staging '+name.rsplit('-', 1)[-1]}})
        record[name] = email
    endpoint = f'https://sqladmin.googleapis.com/sql/v1beta4/projects/{PROJECT}/instances'
    current = api(session, 'GET', endpoint+'/'+SQL, missing=True)
    if current is None:
        operation = api(session, 'POST', endpoint, json={'name': SQL, 'region': REGION,
            'databaseVersion': 'POSTGRES_16', 'rootPassword': admin_password,
            'settings': {'tier': 'db-g1-small', 'edition': 'ENTERPRISE', 'availabilityType': 'ZONAL',
                'activationPolicy': 'ALWAYS', 'dataDiskSizeGb': '10', 'dataDiskType': 'PD_SSD',
                'storageAutoResize': True, 'storageAutoResizeLimit': '30', 'deletionProtectionEnabled': True,
                'ipConfiguration': {'ipv4Enabled': True, 'authorizedNetworks': [], 'sslMode': 'ENCRYPTED_ONLY'},
                'backupConfiguration': {'enabled': True, 'startTime': '05:00', 'pointInTimeRecoveryEnabled': True,
                    'transactionLogRetentionDays': 7,
                    'backupRetentionSettings': {'retainedBackups': 7, 'retentionUnit': 'COUNT'}},
                'userLabels': LABELS}})
        record['sqlOperation'] = operation['name']
        save(record)
        print('Started dedicated PostgreSQL instance creation.', flush=True)
    else:
        require_labels(current['settings'].get('userLabels', {}))
        print('Dedicated PostgreSQL state: '+current['state'], flush=True)
    endpoint = f'https://redis.googleapis.com/v1/projects/{PROJECT}/locations/{REGION}/instances'
    current = api(session, 'GET', endpoint+'/'+REDIS, missing=True)
    if current is None:
        operation = api(session, 'POST', endpoint, params={'instanceId': REDIS}, json={
            'displayName': 'CookCredit hiring staging rate limits', 'tier': 'BASIC', 'memorySizeGb': 1,
            'redisVersion': 'REDIS_7_2', 'authorizedNetwork': f'projects/{PROJECT}/global/networks/default',
            'connectMode': 'DIRECT_PEERING', 'authEnabled': True,
            'transitEncryptionMode': 'SERVER_AUTHENTICATION', 'labels': LABELS})
        record['redisOperation'] = operation['name']
        save(record)
        print('Started dedicated Redis creation with TLS and AUTH.', flush=True)
    else:
        require_labels(current.get('labels', {}))
        print('Dedicated Redis state: '+current['state'], flush=True)
    record.update(service=SERVICE, sql=SQL, redis=REDIS)
    save(record)


def bind(session, resource, member, role):
    """Add exactly one binding and preserve every unrelated role/member/etag."""
    current = (api(session, 'GET', resource+':getIamPolicy') if resource.startswith('https://run.googleapis.com/v2/')
               else api(session, 'POST', resource+':getIamPolicy', json={}))
    policy = current
    bindings = policy.setdefault('bindings', [])
    match = next((b for b in bindings if b['role'] == role and not b.get('condition')), None)
    if match is None:
        bindings.append({'role': role, 'members': [member]})
    elif member not in match.get('members', []):
        match.setdefault('members', []).append(member)
    else:
        return
    api(session, 'POST', resource+':setIamPolicy', json={'policy': policy})


def configure():
    session = client()
    record = state()
    services = ['recaptchaenterprise.googleapis.com', 'firebaseappcheck.googleapis.com',
                'iamcredentials.googleapis.com', 'cloudscheduler.googleapis.com']
    api(session, 'POST', f'https://serviceusage.googleapis.com/v1/projects/{NUMBER}/services:batchEnable',
        json={'serviceIds': services})
    runtime = f'{RUNTIME}@{PROJECT}.iam.gserviceaccount.com'
    migrator = f'{MIGRATOR}@{PROJECT}.iam.gserviceaccount.com'
    worker = f'{WORKER}@{PROJECT}.iam.gserviceaccount.com'
    project_resource = f'https://cloudresourcemanager.googleapis.com/v1/projects/{PROJECT}'
    for email in (runtime, migrator):
        bind(session, project_resource, 'serviceAccount:'+email, 'roles/cloudsql.client')
    # Secret Manager uses GET for getIamPolicy (the IAM APIs above use POST).
    allocations = {
        runtime: ['STG_DB_RUNTIME_PASS', 'STG_INTERNAL_SECRET', 'STG_API_KEY_PEPPER',
                  'STG_SESSION_SECRET', 'STG_WEBHOOK_ENCRYPTION_KEY',
                  'GEOCODING_API_KEY', 'LOCATION_TOKEN_SECRET'],
        migrator: ['STG_DB_ADMIN_PASS', 'STG_DB_RUNTIME_PASS'],
    }
    for email, names in allocations.items():
        for name in names:
            endpoint = f'https://secretmanager.googleapis.com/v1/projects/{PROJECT}/secrets/COOKCREDIT_HIRING_{name}'
            policy = api(session, 'GET', endpoint+':getIamPolicy')
            bindings = policy.setdefault('bindings', [])
            role = 'roles/secretmanager.secretAccessor'
            match = next((b for b in bindings if b['role'] == role and not b.get('condition')), None)
            member = 'serviceAccount:'+email
            if match is None:
                bindings.append({'role': role, 'members': [member]})
            elif member not in match.get('members', []):
                match.setdefault('members', []).append(member)
            else:
                continue
            api(session, 'POST', endpoint+':setIamPolicy', json={'policy': policy})
    worker_resource = f'https://iam.googleapis.com/v1/projects/{PROJECT}/serviceAccounts/{worker}'
    bind(session, worker_resource, 'serviceAccount:'+runtime, 'roles/iam.serviceAccountUser')
    bind(session, worker_resource, f'serviceAccount:service-{NUMBER}@gcp-sa-cloudtasks.iam.gserviceaccount.com',
         'roles/iam.serviceAccountTokenCreator')
    # Own identity only: required for ADC-backed short-lived signed media URLs.
    runtime_resource = f'https://iam.googleapis.com/v1/projects/{PROJECT}/serviceAccounts/{runtime}'
    bind(session, runtime_resource, 'serviceAccount:'+runtime, 'roles/iam.serviceAccountTokenCreator')
    endpoint = f'https://cloudtasks.googleapis.com/v2/projects/{PROJECT}/locations/{REGION}/queues/{QUEUE}'
    current = api(session, 'GET', endpoint, missing=True)
    if current is None:
        current = api(session, 'POST', endpoint.rsplit('/', 1)[0], json={
            'name': f'projects/{PROJECT}/locations/{REGION}/queues/{QUEUE}',
            'rateLimits': {'maxDispatchesPerSecond': 1, 'maxConcurrentDispatches': 2},
            'retryConfig': {'maxAttempts': 8, 'minBackoff': '10s', 'maxBackoff': '300s', 'maxDoublings': 5}})
    bind(session, endpoint, 'serviceAccount:'+runtime, 'roles/cloudtasks.enqueuer')
    repo = f'https://artifactregistry.googleapis.com/v1/projects/{PROJECT}/locations/{REGION}/repositories/cookcredit-hiring'
    if api(session, 'GET', repo, missing=True) is None:
        api(session, 'POST', repo.rsplit('/', 1)[0], params={'repositoryId': 'cookcredit-hiring'},
            json={'format': 'DOCKER', 'description': 'CookCredit hiring release images', 'labels': LABELS})
    endpoint = 'https://storage.googleapis.com/storage/v1/b/'+BUCKET
    current = api(session, 'GET', endpoint, missing=True)
    if current is None:
        api(session, 'POST', endpoint.rsplit('/', 1)[0], params={'project': PROJECT}, json={
            'name': BUCKET, 'location': REGION, 'labels': LABELS,
            'iamConfiguration': {'uniformBucketLevelAccess': {'enabled': True}, 'publicAccessPrevention': 'enforced'},
            'lifecycle': __import__('media_lifecycle').hiring_media_lifecycle()})
    else:
        require_labels(current.get('labels', {}))
    policy = api(session, 'GET', endpoint+'/iam')
    bindings = policy.setdefault('bindings', [])
    member = 'serviceAccount:'+runtime
    if not any(b['role'] == 'roles/storage.objectUser' and member in b.get('members', []) for b in bindings):
        bindings.append({'role': 'roles/storage.objectUser', 'members': [member]})
        api(session, 'PUT', endpoint+'/iam', json=policy)
    endpoint = f'https://firebasehosting.googleapis.com/v1beta1/projects/{PROJECT}/sites/{SITE}'
    if api(session, 'GET', endpoint, missing=True) is None:
        api(session, 'POST', endpoint.rsplit('/', 1)[0], params={'siteId': SITE}, json={})
    record.update(site=SITE, bucket=BUCKET, queue=QUEUE)
    save(record)
    print('Configured dedicated identities, scoped secrets, queue, media bucket, registry and hosting site.', flush=True)
    endpoint = f'https://firebase.googleapis.com/v1beta1/projects/{PROJECT}/webApps'
    apps = api(session, 'GET', endpoint).get('apps', [])
    matches = [app for app in apps if app.get('displayName') == 'CookCredit Hiring Staging']
    if len(matches) > 1:
        raise RuntimeError('Duplicate Firebase staging app names')
    if matches:
        record['firebaseApp'] = matches[0]['appId']
    elif not record.get('firebaseAppOperation'):
        operation = api(session, 'POST', endpoint, json={'displayName': 'CookCredit Hiring Staging'})
        record['firebaseAppOperation'] = operation['name']
    save(record)


def status():
    session = client()
    for name, endpoint in (
        ('sql', f'https://sqladmin.googleapis.com/sql/v1beta4/projects/{PROJECT}/instances/{SQL}'),
        ('redis', f'https://redis.googleapis.com/v1/projects/{PROJECT}/locations/{REGION}/instances/{REDIS}')):
        resource = api(session, 'GET', endpoint)
        print(json.dumps({'resource': name, 'state': resource.get('state')}))


def grant_secret(session, name, email):
    endpoint = f'https://secretmanager.googleapis.com/v1/projects/{PROJECT}/secrets/{name}'
    policy = api(session, 'GET', endpoint+':getIamPolicy')
    member = 'serviceAccount:'+email
    role = 'roles/secretmanager.secretAccessor'
    bindings = policy.setdefault('bindings', [])
    match = next((b for b in bindings if b['role'] == role and not b.get('condition')), None)
    if match is None:
        bindings.append({'role': role, 'members': [member]})
    elif member not in match.get('members', []):
        match.setdefault('members', []).append(member)
    else:
        return
    api(session, 'POST', endpoint+':setIamPolicy', json={'policy': policy})


def data():
    session = client()
    record = state()
    instance = f'https://sqladmin.googleapis.com/sql/v1beta4/projects/{PROJECT}/instances/{SQL}'
    sql = api(session, 'GET', instance)
    require_labels(sql['settings'].get('userLabels', {}))
    if sql['state'] != 'RUNNABLE':
        raise RuntimeError('Staging SQL is not ready')
    database = 'cookcredit_hiring_staging'
    if api(session, 'GET', instance+'/databases/'+database, missing=True) is None:
        operation = api(session, 'POST', instance+'/databases', json={'name': database})
        record['databaseOperation'] = operation['name']
        save(record)
    endpoint = f'https://redis.googleapis.com/v1/projects/{PROJECT}/locations/{REGION}/instances/{REDIS}'
    redis = api(session, 'GET', endpoint)
    require_labels(redis.get('labels', {}))
    if redis['state'] != 'READY' or redis.get('transitEncryptionMode') != 'SERVER_AUTHENTICATION':
        raise RuntimeError('Staging Redis TLS is not ready')
    password = api(session, 'GET', endpoint+'/authString')['authString']
    certs = redis.get('serverCaCerts') or []
    if not certs:
        raise RuntimeError('Redis CA certificate unavailable')
    ca = ''.join(cert['cert'] for cert in certs)
    url = f'rediss://:{quote(password, safe="")}@{redis["host"]}:{redis["port"]}/0?ssl_ca_certs=/secrets/redis/ca.pem&ssl_cert_reqs=required&socket_connect_timeout=5&socket_timeout=5'
    secret_value(session, 'COOKCREDIT_HIRING_STG_REDIS_URL', lambda: url)
    secret_value(session, 'COOKCREDIT_HIRING_STG_REDIS_CA', lambda: ca)
    for name in ('COOKCREDIT_HIRING_STG_REDIS_URL', 'COOKCREDIT_HIRING_STG_REDIS_CA'):
        grant_secret(session, name, f'{RUNTIME}@{PROJECT}.iam.gserviceaccount.com')
    endpoint = 'https://storage.googleapis.com/storage/v1/b/'+BUCKET
    bucket = api(session, 'GET', endpoint)
    require_labels(bucket.get('labels', {}))
    api(session, 'PATCH', endpoint, params={'ifMetagenerationMatch': bucket['metageneration']}, json={
        'cors': [{'origin': ['https://'+SITE+'.web.app', 'https://'+SITE+'.firebaseapp.com'],
                  'method': ['GET', 'HEAD', 'PUT'], 'responseHeader': ['Content-Type'], 'maxAgeSeconds': 600}]})
    record.update(database=database, sqlConnection=sql['connectionName'], redisTls=True)
    save(record)
    print('Dedicated database and TLS Redis secrets are ready; media CORS is limited to the staging site.')


def firebase():
    session = client()
    record = state()
    if record.get('sharedCookCreditAuth'):
        raise RuntimeError('Shared CookCredit Auth is configured; use firebase_shared_auth instead.')
    if not record.get('firebaseApp'):
        operation = api(session, 'GET', 'https://firebase.googleapis.com/v1beta1/'+record['firebaseAppOperation'])
        if not operation.get('done') or not operation.get('response', {}).get('appId'):
            raise RuntimeError('Firebase staging web app creation has not completed')
        record['firebaseApp'] = operation['response']['appId']
        save(record)
    config = api(session, 'GET', f'https://firebase.googleapis.com/v1beta1/projects/{PROJECT}/webApps/{record["firebaseApp"]}/config')
    # SDK configuration is public; explicitly allowlist its fields, never export auth admin configuration.
    record['firebaseConfig'] = {k: config[k] for k in ('projectId', 'appId', 'apiKey', 'authDomain', 'messagingSenderId') if k in config}
    record['firebaseConfig']['storageBucket'] = BUCKET
    endpoint = f'https://recaptchaenterprise.googleapis.com/v1/projects/{PROJECT}/keys'
    keys = api(session, 'GET', endpoint).get('keys', [])
    keys = [key for key in keys if key.get('displayName') == 'CookCredit hiring staging App Check']
    if len(keys) > 1:
        raise RuntimeError('Duplicate staging reCAPTCHA keys')
    if keys:
        key = keys[0]
        require_labels(key.get('labels', {}))
    else:
        key = api(session, 'POST', endpoint, json={
            'displayName': 'CookCredit hiring staging App Check', 'labels': LABELS,
            'webSettings': {'allowedDomains': [SITE+'.web.app', SITE+'.firebaseapp.com'], 'integrationType': 'SCORE'}})
    record['recaptchaSiteKey'] = key['name'].rsplit('/', 1)[-1]
    save(record)
    name = f'projects/{NUMBER}/apps/{record["firebaseApp"]}/recaptchaEnterpriseConfig'
    api(session, 'PATCH', 'https://firebaseappcheck.googleapis.com/v1/'+name,
        params={'updateMask': 'siteKey,tokenTtl'},
        json={'name': name, 'siteKey': record['recaptchaSiteKey'], 'tokenTtl': '3600s'})
    endpoint = f'https://identitytoolkit.googleapis.com/admin/v2/projects/{PROJECT}/config'
    auth = api(session, 'GET', endpoint)
    if not auth.get('signIn', {}).get('email', {}).get('enabled'):
        raise RuntimeError('Email/password sign-in is disabled in the staging project')
    domains = auth.get('authorizedDomains', [])
    for domain in (SITE+'.web.app', SITE+'.firebaseapp.com'):
        if domain not in domains:
            domains.append(domain)
    api(session, 'PATCH', endpoint, params={'updateMask': 'authorizedDomains'}, json={'authorizedDomains': domains})
    save(record)
    print('Staging Firebase web app, domain-restricted App Check and authorized domains are configured.')


def firebase_shared_auth():
    """New staging-only web app; reuse CookCredit login without live data grants.

    No Auth users, templates, existing app settings, Firestore rules or live
    storage permissions are changed. The staging SA only verifies signed tokens.
    """
    session, record = client(), state()
    project, number = 'foodnlit-1123e', '319305393408'
    base = f'https://firebase.googleapis.com/v1beta1/projects/{project}/webApps'
    display = 'CookCredit Hiring Staging'
    apps = api(session, 'GET', base, params={'pageSize': 100}).get('apps', [])
    matches = [app for app in apps if app.get('displayName') == display]
    if len(matches) > 1:
        raise RuntimeError('Duplicate hiring staging web apps in CookCredit Auth')
    if not matches:
        pending = record.get('sharedAuthAppOperation')
        if pending:
            operation = api(session, 'GET', 'https://firebase.googleapis.com/v1beta1/'+pending)
            if not operation.get('done'):
                print('CookCredit staging Auth app is still provisioning.'); return
            if operation.get('error'):
                raise RuntimeError('Staging Auth app provisioning failed')
            app = operation['response']
        else:
            operation = api(session, 'POST', base, json={'displayName': display})
            record['sharedAuthAppOperation'] = operation['name']; save(record)
            print('Created a separate staging web-app registration in CookCredit Auth.'); return
    else:
        app = matches[0]
    config = api(session, 'GET', base+'/'+app['appId']+'/config')
    record.setdefault('isolatedAuthConfig', record['firebaseConfig'])
    record.setdefault('isolatedAuthApp', record['firebaseApp'])
    record.setdefault('isolatedAuthRecaptcha', record['recaptchaSiteKey'])
    record['firebaseConfig'] = {k: config[k] for k in ('projectId', 'appId', 'apiKey', 'authDomain', 'messagingSenderId') if k in config}
    record['firebaseConfig']['storageBucket'] = BUCKET
    record['firebaseApp'] = app['appId']
    endpoint = f'https://recaptchaenterprise.googleapis.com/v1/projects/{project}/keys'
    keys = [key for key in api(session, 'GET', endpoint).get('keys', [])
            if key.get('displayName') == display+' App Check']
    if len(keys) > 1:
        raise RuntimeError('Duplicate hiring staging App Check keys')
    if keys:
        key = keys[0]; require_labels(key.get('labels', {}))
    else:
        key = api(session, 'POST', endpoint, json={'displayName': display+' App Check', 'labels': LABELS,
            'webSettings': {'allowedDomains': [SITE+'.web.app', SITE+'.firebaseapp.com'], 'integrationType': 'SCORE'}})
    record['recaptchaSiteKey'] = key['name'].rsplit('/', 1)[-1]
    name = f'projects/{number}/apps/{app["appId"]}/recaptchaEnterpriseConfig'
    api(session, 'PATCH', 'https://firebaseappcheck.googleapis.com/v1/'+name,
        params={'updateMask': 'siteKey,tokenTtl'}, json={'name': name, 'siteKey': record['recaptchaSiteKey'], 'tokenTtl': '3600s'})
    endpoint = f'https://identitytoolkit.googleapis.com/admin/v2/projects/{project}/config'
    auth_config = api(session, 'GET', endpoint)
    mail = auth_config.get('notification', {}).get('sendEmail', {})
    if mail.get('callbackUri') != 'https://cookcredit.com/__/auth/action':
        raise RuntimeError('CookCredit branded email callback is not configured')
    domains = auth_config.get('authorizedDomains', [])
    updated = list(dict.fromkeys(domains+[SITE+'.web.app', SITE+'.firebaseapp.com']))
    if updated != domains:
        api(session, 'PATCH', endpoint, params={'updateMask': 'authorizedDomains'}, json={'authorizedDomains': updated})
    record.update(sharedCookCreditAuth=True, emailBrandAccepted='CookCredit', emailInboxConfirmed=True)
    save(record)
    print('Separate staging app and App Check ready; CookCredit accounts shared, data permissions unchanged.')


def build(capacity=True):
    """Test a secret-free source snapshot, then publish exactly that snapshot's image."""
    backend = Path(__file__).resolve().parents[1] / 'backend'
    result = subprocess.run(['gcloud.cmd' if os.name == 'nt' else 'gcloud', 'meta', 'list-files-for-upload',
        '--account='+ACCOUNT, '--project='+PROJECT], cwd=backend, capture_output=True, text=True, check=True)
    files = result.stdout.strip().splitlines()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ').lower()
    archive = STATE_FILE.parent / ('hiring-staging-'+stamp+'.tar.gz')
    with tarfile.open(archive, 'w:gz') as bundle:
        for name in files:
            path = (backend/name).resolve()
            if not path.is_relative_to(backend.resolve()):
                raise RuntimeError('Source archive path escaped the backend')
            if ((path.name.startswith('.env') and path.name != '.env.example')
                    or path.suffix in ('.key', '.pem')
                    or path.name in ('serviceAccountKey.json', 'firebase-credentials.json')):
                raise RuntimeError('Credential file rejected from source archive')
            bundle.add(path, arcname=path.relative_to(backend).as_posix(), recursive=False)
    session = client()
    bucket = PROJECT+'_cloudbuild'
    name = 'source/'+archive.name
    uploaded = api(session, 'POST', f'https://storage.googleapis.com/upload/storage/v1/b/{bucket}/o',
        params={'uploadType': 'media', 'name': name, 'ifGenerationMatch': '0'},
        headers={'Content-Type': 'application/gzip'}, data=archive.read_bytes())
    config = yaml.safe_load((backend/'cloudbuild.verify.yaml').read_text())
    if not capacity:
        config['steps'] = [step for step in config['steps']
                           if 'scripts/verify_ephemeral_load.py' not in step.get('args', [])]
    config['source'] = {'storageSource': {'bucket': bucket, 'object': name, 'generation': uploaded['generation']}}
    image = f'{REGION}-docker.pkg.dev/{PROJECT}/cookcredit-hiring/api:{stamp}'
    config['steps'].append({'name': 'gcr.io/cloud-builders/docker', 'args': ['build', '-t', image, '-f', 'Dockerfile', '.']})
    config['images'] = [image]
    config['tags'] = ['cookcredit-hiring-staging']
    operation = api(session, 'POST', f'https://cloudbuild.googleapis.com/v1/projects/{PROJECT}/builds', json=config)
    record = state()
    record['build'] = operation['metadata']['build']['id']
    record['buildIncludesCapacity'] = capacity
    record['imageTag'] = image
    record.pop('imageDigest', None)
    save(record)
    print(json.dumps({'buildId': record['build'], 'sourceFiles': len(files), 'imageTag': image}))


def build_functional():
    build(capacity=False)


def build_status():
    record = state()
    result = api(client(), 'GET', f'https://cloudbuild.googleapis.com/v1/projects/{PROJECT}/builds/{record["build"]}')
    if result['status'] == 'SUCCESS':
        images = result.get('results', {}).get('images', [])
        image = next(image for image in images if image['name'] == record['imageTag'])
        record['imageDigest'] = image['name'].rsplit(':', 1)[0]+'@'+image['digest']
        save(record)
    print(json.dumps({'buildId': record['build'], 'status': result['status'],
                      'image': record.get('imageDigest'), 'steps': [step.get('status') for step in result.get('steps', [])]}))


def env_values(values, secrets_map=None):
    result = [{'name': name, 'value': str(value)} for name, value in values.items()]
    for name, secret in (secrets_map or {}).items():
        result.append({'name': name, 'valueSource': {'secretKeyRef': {'secret': secret, 'version': '1'}}})
    return result


def sql_volume():
    return {'name': 'cloudsql', 'cloudSqlInstance': {'instances': [f'{PROJECT}:{REGION}:{SQL}']}}


def migration_job():
    record = state()
    if not record.get('imageDigest'):
        raise RuntimeError('A successful tested release build is required')
    session = client()
    name = f'projects/{PROJECT}/locations/{REGION}/jobs/{MIGRATOR}'
    endpoint = 'https://run.googleapis.com/v2/'+name
    current = api(session, 'GET', endpoint, missing=True)
    body = {'name': name, 'labels': LABELS, 'template': {'taskCount': 1, 'parallelism': 1,
        'template': {'serviceAccount': f'{MIGRATOR}@{PROJECT}.iam.gserviceaccount.com',
        'maxRetries': 0, 'timeout': '600s', 'volumes': [sql_volume()], 'containers': [{
            'image': record['imageDigest'], 'command': ['python'], 'args': ['scripts/bootstrap_hiring_staging_db.py'],
            'resources': {'limits': {'cpu': '1', 'memory': '512Mi'}},
            'volumeMounts': [{'name': 'cloudsql', 'mountPath': '/cloudsql'}],
            'env': env_values({'COOKCREDIT_ENVIRONMENT': 'staging', 'CLOUD_SQL_CONNECTION': record['sqlConnection'],
                'DB_USER': 'postgres', 'DB_NAME': record['database']},
                {'DB_PASS': 'COOKCREDIT_HIRING_STG_DB_ADMIN_PASS', 'RUNTIME_DB_PASS': 'COOKCREDIT_HIRING_STG_DB_RUNTIME_PASS'})
        }]}}}
    if current:
        require_labels(current.get('labels', {}))
        body['etag'] = current['etag']
        operation = api(session, 'PATCH', endpoint, json=body)
    else:
        body.pop('name', None)
        operation = api(session, 'POST', endpoint.rsplit('/', 1)[0], params={'jobId': MIGRATOR}, json=body)
    record['migrationJobOperation'] = operation['name']
    save(record)
    print('Prepared the migration job for the dedicated staging database.')


def migrate():
    session = client()
    record = state()
    endpoint = f'https://run.googleapis.com/v2/projects/{PROJECT}/locations/{REGION}/jobs/{MIGRATOR}'
    job = api(session, 'GET', endpoint)
    require_labels(job.get('labels', {}))
    if job.get('reconciling') or job.get('terminalCondition', {}).get('state') != 'CONDITION_SUCCEEDED':
        raise RuntimeError('Migration job is not ready')
    operation = api(session, 'POST', endpoint+':run', json={})
    record['migrationOperation'] = operation['name']
    record['migrationImage'] = record['imageDigest']
    record['migrationSucceeded'] = False
    save(record)
    print('Started staging database migrations with the separate migration identity.')


def migration_status():
    record = state()
    operation = api(client(), 'GET', 'https://run.googleapis.com/v2/'+record['migrationOperation'])
    succeeded = bool(operation.get('done') and not operation.get('error') and operation.get('response', {}).get('succeededCount') == 1)
    record['migrationSucceeded'] = succeeded
    save(record)
    print(json.dumps({'done': operation.get('done', False), 'succeeded': succeeded,
        'error': operation.get('error', {}).get('message'), 'execution': operation.get('response', {}).get('name')}))


def owner_access_config(record):
    """Explicit release opt-ins; this function performs no cloud or mail actions."""
    enabled = record.get('ownerAccessReviewed') is True
    inbox = record.get('ownerAccessInboxReviewed') is True
    if inbox and not enabled:
        raise RuntimeError('Inbox import requires reviewed owner access')
    if enabled and record.get('googleSmtpAuthenticated') is not True:
        raise RuntimeError('Owner access requires the existing verified Google mail configuration')
    if inbox and record.get('ownerAccessInboxSecretsReady') is not True:
        raise RuntimeError('Both dedicated inbox secrets and runtime access must be verified first')
    values = {'HIRING_ACCESS_APPROVALS_ENABLED': '1' if enabled else '0',
              'HIRING_ACCESS_INBOX_ENABLED': '1' if inbox else '0'}
    secret_refs = ({'HIRING_INBOX_CONTACT_APP_PASSWORD': 'HIRING_INBOX_CONTACT_APP_PASSWORD',
                    'HIRING_INBOX_OWNER_APP_PASSWORD': 'HIRING_INBOX_OWNER_APP_PASSWORD'} if inbox else {})
    # The existing cc-hiring-stg-emails job owns account mail delivery.
    # Never provision a second sender or change its one-minute schedule here.
    jobs = []
    if inbox:
        jobs.append(('cc-hiring-stg-access-inbox', '/api/access/internal/sync-inbox'))
    return values, secret_refs, jobs


def validate_owner_email_schedule(job, origin):
    """Validate the existing sender without modifying or triggering it."""
    target = (job or {}).get('httpTarget', {})
    oidc = target.get('oidcToken', {})
    if (not job or job.get('state') != 'ENABLED'
            or target.get('uri') != origin.rstrip('/') + '/api/auth/internal/dispatch-emails'
            or target.get('httpMethod') != 'POST'
            or oidc.get('audience') != origin
            or oidc.get('serviceAccountEmail') != f'{WORKER}@{PROJECT}.iam.gserviceaccount.com'):
        raise RuntimeError('Review the existing cc-hiring-stg-emails schedule before enabling owner access')


def deploy_api():
    record = state()
    if not record.get('migrationSucceeded') or record.get('migrationImage') != record.get('imageDigest'):
        raise RuntimeError('This release must pass staging migrations before deployment')
    session = client()
    name = f'projects/{PROJECT}/locations/{REGION}/services/{SERVICE}'
    endpoint = 'https://run.googleapis.com/v2/'+name
    current = api(session, 'GET', endpoint, missing=True)
    # Cloud Run's documented deterministic URL; checked against returned urls before release.
    origin = f'https://{SERVICE}-{NUMBER}.{REGION}.run.app'
    worker = f'{WORKER}@{PROJECT}.iam.gserviceaccount.com'
    runtime = f'{RUNTIME}@{PROJECT}.iam.gserviceaccount.com'
    values = {
        'COOKCREDIT_ENVIRONMENT': 'staging', 'FLASK_ENV': 'production', 'MARKET': 'US',
        'FRONTEND_URL': f'https://{SITE}.web.app,https://{SITE}.firebaseapp.com,https://cookcredit-knife-demo.web.app', 'PUBLIC_API_URL': origin,
        'ASSESSMENT_PUBLIC_URL': 'https://cookcredit-knife-demo.web.app/hiring/',
        'ASSESSMENT_BRIDGE_ENABLED': '1' if record.get('stagingAssessmentReviewEnabled') else '0',
        'ASSESSMENT_EMPLOYMENT_VALIDATED': '0',
        'ENGINE_APPLICANT_IMPORT_ENABLED': '1',
        'STAGING_ALLOWED_EMAILS': 'eassefa@cookcredit.com,termias18@gmail.com,staging-smoke@cookcredit.invalid',
        'PARTNER_INTEGRATIONS_ENABLED': '1', 'BUSINESS_BILLING_ENABLED': '0',
        'INTEGRATION_EARLY_ACCESS_ENABLED': '1', 'EARLY_ACCESS_MONTHLY_ASSESSMENT_LIMIT': '100',
        'AUTH_EMAILS_ENABLED': '1' if record.get('sharedCookCreditAuth') and record.get('emailInboxConfirmed') else '0',
        'AUTH_WELCOME_EMAILS_ENABLED': '0', 'AUTH_EMAIL_PROVIDER': 'firebase', 'BEAM_AGENT_ENABLED': '0',
        'LOCATION_SEARCH_ENABLED': '1', 'AUTH_APP_CHECK_REQUIRED': '1', 'FIREBASE_USE_ADC': '1',
        'FIREBASE_PROJECT_ID': record['firebaseConfig']['projectId'], 'FIREBASE_STORAGE_BUCKET': BUCKET,
        'FIREBASE_APP_CHECK_APP_IDS': record['firebaseApp']+',1:319305393408:web:156dd95582a241938ebfe5',
        'STORAGE_SIGNING_SERVICE_ACCOUNT': runtime,
        'COOKCREDIT_EXPECT_MULTI_INSTANCE': '1', 'DB_USER': 'hiring_runtime', 'DB_NAME': record['database'],
        'CLOUD_SQL_CONNECTION': record['sqlConnection'], 'DB_POOL_SIZE': '3', 'DB_MAX_OVERFLOW': '2',
        'GUNICORN_WORKERS': '1', 'GUNICORN_THREADS': '4', 'SCORING_ALLOW_INLINE': '0',
        'TASKS_QUEUE': f'projects/{PROJECT}/locations/{REGION}/queues/{QUEUE}',
        'TASKS_TARGET_URL': origin+'/api/skills/recompute', 'TASKS_OIDC_SA': worker, 'TASKS_OIDC_AUDIENCE': origin,
    }
    secrets_map = {'DB_PASS': 'STG_DB_RUNTIME_PASS', 'INTERNAL_SECRET': 'STG_INTERNAL_SECRET',
        'PARTNER_API_KEY_PEPPER': 'STG_API_KEY_PEPPER', 'SECRET_KEY': 'STG_SESSION_SECRET',
        'WEBHOOK_SECRET_ENCRYPTION_KEY': 'STG_WEBHOOK_ENCRYPTION_KEY', 'REDIS_URL': 'STG_REDIS_URL',
        'GOOGLE_GEOCODING_API_KEY': 'GEOCODING_API_KEY', 'LOCATION_TOKEN_SECRET': 'LOCATION_TOKEN_SECRET'}
    if record.get('googleSmtpAuthenticated'):
        values.update(AUTH_EMAIL_PROVIDER='google_smtp', AUTH_EMAILS_ENABLED='1', AUTH_WELCOME_EMAILS_ENABLED='1',
            GOOGLE_SMTP_USER=ACCOUNT, AUTH_EMAIL_TEST_RECIPIENTS='eassefa@cookcredit.com,termias18@gmail.com')
        secrets_map['GOOGLE_SMTP_APP_PASSWORD'] = 'GOOGLE_SMTP_APP_PASSWORD'
    access_values, access_secrets, _ = owner_access_config(record)
    values.update(access_values)
    secrets_map.update(access_secrets)
    body = {'name': name, 'labels': LABELS, 'description': 'Isolated CookCredit hiring staging; invited testers only',
        'ingress': 'INGRESS_TRAFFIC_ALL', 'template': {'labels': LABELS, 'serviceAccount': runtime,
            'scaling': {'minInstanceCount': 1, 'maxInstanceCount': 3}, 'maxInstanceRequestConcurrency': 16,
            'timeout': '300s', 'executionEnvironment': 'EXECUTION_ENVIRONMENT_GEN2',
            'vpcAccess': {'egress': 'PRIVATE_RANGES_ONLY', 'networkInterfaces': [{'network': 'default', 'subnetwork': 'default'}]},
            'volumes': [sql_volume(), {'name': 'redis-ca', 'secret': {
                'secret': 'COOKCREDIT_HIRING_STG_REDIS_CA', 'items': [{'version': '1', 'path': 'ca.pem'}]}}],
            'containers': [{'image': record['imageDigest'], 'ports': [{'containerPort': 8080}],
                'resources': {'limits': {'cpu': '1', 'memory': '1Gi'}, 'cpuIdle': True, 'startupCpuBoost': True},
                'env': env_values(values, {key: 'COOKCREDIT_HIRING_'+val for key, val in secrets_map.items()}),
                'volumeMounts': [{'name': 'cloudsql', 'mountPath': '/cloudsql'}, {'name': 'redis-ca', 'mountPath': '/secrets/redis'}],
                'startupProbe': {'httpGet': {'path': '/api/ready', 'port': 8080},
                    'timeoutSeconds': 5, 'periodSeconds': 10, 'failureThreshold': 24}}]}}
    if current:
        require_labels(current.get('labels', {}))
        body['etag'] = current['etag']
        operation = api(session, 'PATCH', endpoint, params={'updateMask': 'template,description'}, json=body)
    else:
        body.pop('name', None)
        operation = api(session, 'POST', endpoint.rsplit('/', 1)[0], params={'serviceId': SERVICE}, json=body)
    record.pop('apiReadyRevision', None)
    record.update(apiOrigin=origin, apiOperation=operation['name'])
    save(record)
    print('Deploying the tested image with shared TLS rate limits, capped scaling and dependency readiness probes.')


def api_status():
    record = state()
    session = client()
    endpoint = f'https://run.googleapis.com/v2/projects/{PROJECT}/locations/{REGION}/services/{SERVICE}'
    service = api(session, 'GET', endpoint)
    require_labels(service.get('labels', {}))
    ready = not service.get('reconciling') and service.get('terminalCondition', {}).get('state') == 'CONDITION_SUCCEEDED'
    print(json.dumps({'ready': ready, 'condition': service.get('terminalCondition'), 'urls': service.get('urls')}))
    if ready:
        if record['apiOrigin'] not in service.get('urls', []):
            raise RuntimeError('Expected deterministic API URL was not returned by Cloud Run')
        # Browser endpoints use Firebase JWT + App Check; internal routes verify worker OIDC.
        bind(session, endpoint, 'allUsers', 'roles/run.invoker')
        record['apiReadyRevision'] = service['latestReadyRevision']
        save(record)


def frontend_build():
    record = state()
    frontend = Path(__file__).resolve().parents[1] / 'frontend'
    env = {}
    config = record['firebaseConfig']
    env.update({'VITE_API_URL': record.get('apiOrigin', f'https://{SERVICE}-{NUMBER}.{REGION}.run.app'),
        'VITE_DEPLOYMENT_ENVIRONMENT': 'staging', 'VITE_PREVIEW': '0',
        'VITE_FIREBASE_API_KEY': config['apiKey'], 'VITE_FIREBASE_PROJECT_ID': config['projectId'],
        'VITE_FIREBASE_AUTH_DOMAIN': config['authDomain'], 'VITE_FIREBASE_APP_ID': config['appId'],
        'VITE_HIRING_AUTH_DOMAIN': 'cookcredit.com',
        'VITE_FIREBASE_STORAGE_BUCKET': BUCKET, 'VITE_FIREBASE_MESSAGING_SENDER_ID': config['messagingSenderId'],
        'VITE_RECAPTCHA_ENTERPRISE_SITE_KEY': record['recaptchaSiteKey'],
        'VITE_FIREBASE_EMAIL_BRANDING_READY': '1' if record.get('sharedCookCreditAuth') and record.get('emailInboxConfirmed') else '0',
        'VITE_AUTH_EMAIL_PROVIDER': 'google_smtp' if record.get('googleSmtpAuthenticated') else 'firebase',
        'VITE_AUTH_EMAIL_CONTINUE_URL': 'https://'+SITE+'.web.app/login',
        'VITE_ASSESSMENT_SAME_ORIGIN': '1'})
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ').lower()
    archive = STATE_FILE.parent / ('hiring-frontend-'+stamp+'.tar.gz')
    # Positive allowlist: no local .env, credential files, dependencies or old dist output.
    entries = [frontend/name for name in ('package.json', 'package-lock.json', 'index.html', 'vite.config.js', 'eslint.config.js', 'firebase.json')]
    for folder in ('src', 'public', 'landing', 'scripts', 'tests'):
        entries.extend(path for path in (frontend/folder).rglob('*') if path.is_file())
    with tarfile.open(archive, 'w:gz') as bundle:
        for path in entries:
            if path.suffix in ('.key', '.pem') or path.name.startswith('.env') or not path.resolve().is_relative_to(frontend.resolve()):
                raise RuntimeError('Credential or unexpected path in frontend source')
            bundle.add(path, arcname=path.relative_to(frontend).as_posix(), recursive=False)
    session = client()
    bucket = PROJECT+'_cloudbuild'
    source_name = 'source/'+archive.name
    uploaded = api(session, 'POST', f'https://storage.googleapis.com/upload/storage/v1/b/{bucket}/o',
        params={'uploadType': 'media', 'name': source_name, 'ifGenerationMatch': '0'},
        headers={'Content-Type': 'application/gzip'}, data=archive.read_bytes())
    artifact = 'artifacts/hiring-frontend-'+stamp+'.tar.gz'
    config = {'source': {'storageSource': {'bucket': bucket, 'object': source_name, 'generation': uploaded['generation']}},
        'steps': [{'name': 'node:22', 'entrypoint': 'npm', 'args': ['ci']},
                  {'name': 'node:22', 'entrypoint': 'node', 'args': ['--test', 'tests/accountEmail.test.mjs']},
                  {'name': 'node:22', 'entrypoint': 'node', 'args': ['--test', 'tests/serviceWorkerUpdate.test.mjs']},
                  {'name': 'node:22', 'entrypoint': 'node', 'args': ['--test', 'tests/completeSignup.test.mjs']},
                  {'name': 'node:22', 'entrypoint': 'node', 'args': ['--test', 'tests/hiringNavigation.test.mjs']},
                  {'name': 'node:22', 'entrypoint': 'node', 'args': ['--test', 'tests/profileFailure.test.mjs']},
                  {'name': 'node:22', 'entrypoint': 'npx', 'args': ['eslint', 'src/App.jsx', 'src/utils/homeFor.js', 'src/components/AccountDetails.jsx', 'src/components/AccountShell.jsx', 'src/components/AttemptStatus.jsx', 'src/components/BusinessRoute.jsx', 'src/components/ProtectedRoute.jsx', 'src/components/Shell.jsx', 'src/screens/AccountScreen.jsx', 'src/screens/ApplicantHomeScreen.jsx', 'src/screens/HiringApplicationDetailScreen.jsx', 'src/screens/HiringApplicationScreen.jsx', 'src/screens/CookCreditHelpScreen.jsx', 'src/screens/BusinessProfileScreen.jsx', 'src/screens/BusinessRoleNewScreen.jsx', 'src/screens/BusinessCandidateScreen.jsx', 'src/screens/PreviewScreen.jsx']},
                  {'name': 'node:22', 'entrypoint': 'npx', 'args': ['eslint', 'src/utils/completeSignup.js', 'src/context/AuthContext.jsx', 'src/screens/LoginScreen.jsx', 'src/screens/SignupScreen.jsx', 'src/screens/VerifyEmailScreen.jsx', 'src/screens/ForgotScreen.jsx']},
                  {'name': 'node:22', 'entrypoint': 'npx', 'args': ['eslint', 'src/components/AuthShell.jsx', 'src/components/CookCreditBrand.jsx', 'src/screens/BusinessIntegrationsScreen.jsx', 'src/components/BusinessShell.jsx', 'src/screens/HiringAssessmentReturnScreen.jsx', 'src/components/StagingNotice.jsx', 'src/components/AppUpdateNotice.jsx', 'src/utils/serviceWorkerUpdate.js', 'src/main.jsx', 'src/screens/BusinessLandingScreen.jsx', 'src/config.js']},
                  {'name': 'node:22', 'entrypoint': 'npm', 'args': ['run', 'build'],
                   'env': [key+'='+value for key, value in env.items()]},
                  {'name': 'ubuntu', 'entrypoint': 'tar', 'args': ['-czf', 'staging-dist.tar.gz', '-C', 'dist', '.']},
                  {'name': 'gcr.io/cloud-builders/gsutil', 'args': ['cp', 'staging-dist.tar.gz', 'gs://'+bucket+'/'+artifact]}],
        'timeout': '1200s', 'options': {'logging': 'CLOUD_LOGGING_ONLY'}, 'tags': ['cookcredit-hiring-staging-frontend']}
    operation = api(session, 'POST', f'https://cloudbuild.googleapis.com/v1/projects/{PROJECT}/builds', json=config)
    record.update(frontendBuild=operation['metadata']['build']['id'], frontendArtifact=artifact, frontendBuilt=False)
    save(record)
    print(json.dumps({'buildId': record['frontendBuild'], 'sourceFiles': len(entries)}))


def frontend_dist(record):
    # Build-specific directories prevent old JS bundles surviving a later release.
    build_id = str(UUID(record['frontendBuild']))
    if build_id != record['frontendBuild']:
        raise RuntimeError('Unexpected frontend build identifier')
    frontend = Path(__file__).resolve().parents[1] / 'frontend'
    dist = frontend / 'dist-staging' / build_id
    if not dist.resolve().is_relative_to(frontend.resolve()):
        raise RuntimeError('Frontend output must stay within this workspace')
    return dist


def frontend_status():
    record = state()
    session = client()
    build = api(session, 'GET', f'https://cloudbuild.googleapis.com/v1/projects/{PROJECT}/builds/{record["frontendBuild"]}')
    print(json.dumps({'buildId': record['frontendBuild'], 'status': build['status'],
                      'steps': [step.get('status') for step in build.get('steps', [])]}))
    if build['status'] != 'SUCCESS':
        return
    dist = frontend_dist(record)
    archive = STATE_FILE.parent / 'hiring-staging-frontend-dist.tar.gz'
    response = session.get(f'https://storage.googleapis.com/storage/v1/b/{PROJECT}_cloudbuild/o/'+quote(record['frontendArtifact'], safe=''),
                           params={'alt': 'media'}, timeout=60)
    if not response.ok:
        raise RuntimeError('Cannot retrieve successful frontend build artifact')
    archive.write_bytes(response.content)
    with tarfile.open(archive) as bundle:
        bundle.extractall(dist, filter='data')
    # Validate compiled outputs rather than trusting .env files or the preview server.
    scripts = '\n'.join(path.read_text(encoding='utf-8') for path in (dist/'assets').glob('*.js'))
    if 'Hiring preview' not in scripts or 'Test environment' not in scripts or record['firebaseConfig']['appId'] not in scripts:
        raise RuntimeError('Staging bundle is missing its explicit environment or Firebase app')
    if record.get('apiOrigin', f'https://{SERVICE}-{NUMBER}.{REGION}.run.app') not in scripts:
        raise RuntimeError('Staging bundle does not target its API')
    record['frontendBuilt'] = True
    record['frontendBuiltBuild'] = record['frontendBuild']
    record['frontendArtifactSha256'] = hashlib.sha256(response.content).hexdigest()
    save(record)


def build_evidence():
    record = state()
    result = api(client(), 'POST', 'https://logging.googleapis.com/v2/entries:list', json={
        'resourceNames': ['projects/'+PROJECT],
        'filter': 'resource.type="build" AND resource.labels.build_id="'+record['build']+'" AND '
                  '(textPayload:"passed" OR textPayload:"EPHEMERAL_LOAD" OR textPayload:"p95")',
        'pageSize': 50, 'orderBy': 'timestamp asc'})
    for entry in result.get('entries', []):
        print(entry.get('textPayload', ''))


def probe_job(name='cc-hiring-stg-probe', script='staging_probe.py', extra_env=None):
    session = client()
    record = state()
    if not record.get('apiReadyRevision'):
        raise RuntimeError('Staging API must be ready')
    endpoint = f'https://run.googleapis.com/v2/projects/{PROJECT}/locations/{REGION}/services/{SERVICE}'
    service = api(session, 'GET', endpoint)
    require_labels(service.get('labels', {}))
    template = service['template']
    container = template['containers'][0]
    if container['image'] != record['imageDigest']:
        raise RuntimeError('API no longer uses the tested image')
    endpoint = f'https://run.googleapis.com/v2/projects/{PROJECT}/locations/{REGION}/jobs/{name}'
    current = api(session, 'GET', endpoint, missing=True)
    body = {'labels': LABELS, 'template': {'taskCount': 1, 'parallelism': 1, 'template': {
        'serviceAccount': template['serviceAccount'], 'volumes': template['volumes'],
        'vpcAccess': template['vpcAccess'], 'maxRetries': 0, 'timeout': '600s',
        'containers': [{'image': record['imageDigest'], 'env': container['env']+(extra_env or []),
            'volumeMounts': container['volumeMounts'], 'resources': {'limits': {'cpu': '1', 'memory': '1Gi'}},
            'command': ['python'], 'args': ['-c', Path(__file__).with_name(script).read_text(encoding='utf-8')]}]}}}
    if current:
        require_labels(current.get('labels', {}))
        body.update(name=current['name'], etag=current['etag'])
        api(session, 'PATCH', endpoint, json=body)
    else:
        api(session, 'POST', endpoint.rsplit('/', 1)[0], params={'jobId': name}, json=body)
    print('Prepared the staging-only probe job using the restricted runtime identity.')


def probe_run(name='cc-hiring-stg-probe', operation_key='probeOperation'):
    session = client()
    record = state()
    endpoint = f'https://run.googleapis.com/v2/projects/{PROJECT}/locations/{REGION}/jobs/{name}'
    job = api(session, 'GET', endpoint)
    require_labels(job.get('labels', {}))
    if job.get('reconciling'):
        raise RuntimeError('Probe job is still provisioning')
    operation = api(session, 'POST', endpoint+':run', json={})
    record[operation_key] = operation['name']
    save(record)
    print('Started real cloud API, database privilege, private storage and shared rate-limit probes.')


def probe_status(operation_key='probeOperation', result_key='probeSucceeded'):
    record = state()
    operation = api(client(), 'GET', 'https://run.googleapis.com/v2/'+record[operation_key])
    succeeded = bool(operation.get('done') and not operation.get('error') and operation.get('response', {}).get('succeededCount') == 1)
    record[result_key] = succeeded
    save(record)
    print(json.dumps({'done': operation.get('done', False), 'succeeded': succeeded,
        'error': operation.get('error', {}).get('message'), 'execution': operation.get('response', {}).get('name')}))


def schedules():
    session = client()
    record = state()
    if not record.get('apiReadyRevision'):
        raise RuntimeError('Staging API must be ready')
    _, _, access_jobs = owner_access_config(record)
    existing_mail_name = None
    if record.get('ownerAccessReviewed') is True:
        existing_mail_name = f'projects/{PROJECT}/locations/{REGION}/jobs/cc-hiring-stg-emails'
        existing_mail = api(session, 'GET', 'https://cloudscheduler.googleapis.com/v1/' + existing_mail_name, missing=True)
        validate_owner_email_schedule(existing_mail, record['apiOrigin'])
    worker = f'{WORKER}@{PROJECT}.iam.gserviceaccount.com'
    api(session, 'POST', f'https://serviceusage.googleapis.com/v1beta1/projects/{NUMBER}/services/cloudscheduler.googleapis.com:generateServiceIdentity', json={})
    bind(session, f'https://iam.googleapis.com/v1/projects/{PROJECT}/serviceAccounts/{worker}',
        f'serviceAccount:service-{NUMBER}@gcp-sa-cloudscheduler.iam.gserviceaccount.com', 'roles/iam.serviceAccountTokenCreator')
    base = f'projects/{PROJECT}/locations/{REGION}/jobs/'
    jobs = [('cc-hiring-stg-dispatch', '/api/skills/dispatch-pending'),
            ('cc-hiring-stg-webhooks', '/api/partner/internal/dispatch-webhooks'),
            ('cc-hiring-stg-expiry', '/api/partner/internal/expire-assessment-requests')]
    jobs.extend(access_jobs)
    names = [existing_mail_name] if existing_mail_name else []
    for name, path in jobs:
        endpoint = 'https://cloudscheduler.googleapis.com/v1/'+base+name
        current = api(session, 'GET', endpoint, missing=True)
        description = 'CookCredit isolated hiring staging recovery'
        body = {'name': base+name, 'description': description, 'schedule': '*/5 * * * *', 'timeZone': 'Etc/UTC',
            'attemptDeadline': '300s', 'retryConfig': {'retryCount': 3, 'minBackoffDuration': '15s', 'maxBackoffDuration': '120s'},
            'httpTarget': {'uri': record['apiOrigin']+path, 'httpMethod': 'POST',
                'headers': {'Content-Type': 'application/json'}, 'body': base64.b64encode(b'{}').decode(),
                'oidcToken': {'serviceAccountEmail': worker, 'audience': record['apiOrigin']}}}
        if current:
            if current.get('description') != description:
                raise RuntimeError('Refusing to replace an unrelated scheduler job')
            api(session, 'PATCH', endpoint, params={'updateMask': 'schedule,timeZone,attemptDeadline,retryConfig,httpTarget'}, json=body)
        else:
            api(session, 'POST', endpoint.rsplit('/', 1)[0], json=body)
        names.append(base+name)
        # Access jobs run on their schedule; provisioning must not send mail or import immediately.
        if (name, path) not in access_jobs:
            api(session, 'POST', endpoint+':run', json={})
    record['schedulers'] = names
    save(record)
    print('Configured OIDC-authenticated staging schedules; access jobs were not manually triggered.')


def schedules_status():
    session = client()
    record = state()
    rows = []
    for name in record.get('schedulers', []):
        job = api(session, 'GET', 'https://cloudscheduler.googleapis.com/v1/'+name)
        rows.append({'name': name.rsplit('/', 1)[-1], 'state': job.get('state'),
                     'lastAttemptTime': job.get('lastAttemptTime'), 'status': job.get('status')})
    print(json.dumps(rows))


def queue_logging():
    session = client()
    name = f'projects/{PROJECT}/locations/{REGION}/queues/{QUEUE}'
    api(session, 'PATCH', 'https://cloudtasks.googleapis.com/v2/'+name,
        params={'updateMask': 'stackdriverLoggingConfig'},
        json={'name': name, 'stackdriverLoggingConfig': {'samplingRatio': 1}})
    print('Enabled delivery-status logging on the dedicated staging queue.')


def webhook_receiver():
    session = client()
    record = state()
    account = f'cc-hiring-stg-hooktest@{PROJECT}.iam.gserviceaccount.com'
    endpoint = f'https://iam.googleapis.com/v1/projects/{PROJECT}/serviceAccounts/{account}'
    if api(session, 'GET', endpoint, missing=True) is None:
        api(session, 'POST', endpoint.rsplit('/', 1)[0], json={'accountId': 'cc-hiring-stg-hooktest',
            'serviceAccount': {'displayName': 'CookCredit staging webhook test receiver'}})
    secret_value(session, 'COOKCREDIT_HIRING_STG_PROBE_WEBHOOK_SECRET', lambda: secrets.token_urlsafe(48))
    for secret in ('STG_PROBE_WEBHOOK_SECRET', 'STG_REDIS_URL', 'STG_REDIS_CA'):
        grant_secret(session, 'COOKCREDIT_HIRING_'+secret, account)
    grant_secret(session, 'COOKCREDIT_HIRING_STG_PROBE_WEBHOOK_SECRET', f'{RUNTIME}@{PROJECT}.iam.gserviceaccount.com')
    source = api(session, 'GET', f'https://run.googleapis.com/v2/projects/{PROJECT}/locations/{REGION}/services/{SERVICE}')
    name = 'cookcredit-hiring-stg-hooktest'
    endpoint = f'https://run.googleapis.com/v2/projects/{PROJECT}/locations/{REGION}/services/{name}'
    current = api(session, 'GET', endpoint, missing=True)
    body = {'labels': LABELS, 'description': 'Synthetic CookCredit staging webhook retry receiver; accepts signed test events only',
        'template': {'labels': LABELS, 'serviceAccount': account, 'vpcAccess': source['template']['vpcAccess'],
            'scaling': {'minInstanceCount': 0, 'maxInstanceCount': 1}, 'maxInstanceRequestConcurrency': 8,
            'executionEnvironment': 'EXECUTION_ENVIRONMENT_GEN2', 'timeout': '30s',
            'volumes': [v for v in source['template']['volumes'] if v['name'] == 'redis-ca'],
            'containers': [{'image': record['imageDigest'], 'command': ['python'],
                'args': ['-c', Path(__file__).with_name('staging_webhook_receiver.py').read_text(encoding='utf-8')],
                'ports': [{'containerPort': 8080}], 'resources': {'limits': {'cpu': '1', 'memory': '512Mi'}, 'cpuIdle': True},
                'env': env_values({'COOKCREDIT_ENVIRONMENT': 'staging'}, {'PROBE_WEBHOOK_SECRET': 'COOKCREDIT_HIRING_STG_PROBE_WEBHOOK_SECRET',
                    'REDIS_URL': 'COOKCREDIT_HIRING_STG_REDIS_URL'}),
                'volumeMounts': [{'name': 'redis-ca', 'mountPath': '/secrets/redis'}],
                'startupProbe': {'httpGet': {'path': '/health', 'port': 8080}, 'periodSeconds': 10, 'timeoutSeconds': 5, 'failureThreshold': 24}}]}}
    if current:
        require_labels(current.get('labels', {}))
        body.update(name=current['name'], etag=current['etag'])
        api(session, 'PATCH', endpoint, params={'updateMask': 'template'}, json=body)
    else:
        api(session, 'POST', endpoint.rsplit('/', 1)[0], params={'serviceId': name}, json=body)
    record['webhookReceiver'] = f'https://{name}-{NUMBER}.{REGION}.run.app'
    save(record)
    print('Provisioned a dedicated synthetic webhook receiver with no database or customer storage access.')


def webhook_receiver_status():
    session = client()
    record = state()
    endpoint = f'https://run.googleapis.com/v2/projects/{PROJECT}/locations/{REGION}/services/cookcredit-hiring-stg-hooktest'
    service = api(session, 'GET', endpoint)
    require_labels(service.get('labels', {}))
    ready = not service.get('reconciling') and service.get('terminalCondition', {}).get('state') == 'CONDITION_SUCCEEDED'
    print(json.dumps({'ready': ready, 'condition': service.get('terminalCondition')}))
    if ready:
        assert record['webhookReceiver'] in service.get('urls', [])
        bind(session, endpoint, 'allUsers', 'roles/run.invoker')
        record['webhookReceiverReady'] = True
        save(record)


def webhook_job():
    record = state()
    if not record.get('webhookReceiverReady'):
        raise RuntimeError('Synthetic receiver must be ready')
    probe_job(name='cc-hiring-stg-hookprobe', script='staging_webhook_probe.py', extra_env=env_values(
        {'PROBE_WEBHOOK_URL': record['webhookReceiver']}, {'PROBE_WEBHOOK_SECRET': 'COOKCREDIT_HIRING_STG_PROBE_WEBHOOK_SECRET'}))


def webhook_run():
    probe_run(name='cc-hiring-stg-hookprobe', operation_key='webhookProbeOperation')


def webhook_status():
    probe_status(operation_key='webhookProbeOperation', result_key='webhookProbeSucceeded')


def host_frontend():
    record = state()
    if (not record.get('apiReadyRevision') or not record.get('frontendBuilt')
            or record.get('frontendBuiltBuild') != record.get('frontendBuild')):
        raise RuntimeError('Staging API and compiled frontend must be ready')
    frontend = Path(__file__).resolve().parents[1] / 'frontend'
    dist = frontend_dist(record)
    source = json.loads((frontend/'firebase.json').read_text())['hosting']
    headers = [{'glob': entry['source'], 'headers': {h['key']: h['value'] for h in entry['headers']}}
               for entry in source.get('headers', [])]
    headers.append({'glob': '**', 'headers': {'X-Robots-Tag': 'noindex, nofollow'}})
    config = {'headers': headers, 'rewrites': [{'glob': '**', 'path': '/index.html'}]}
    blobs, paths = {}, {}
    for path in dist.rglob('*'):
        if not path.is_file():
            continue
        if not path.resolve().is_relative_to(dist.resolve()) or path.suffix in ('.key', '.pem', '.map') or path.name.startswith('.env'):
            raise RuntimeError('Unsafe hosting file')
        compressed = gzip.compress(path.read_bytes(), mtime=0)
        digest = hashlib.sha256(compressed).hexdigest()
        blobs[digest] = compressed
        paths['/'+path.relative_to(dist).as_posix()] = digest
    if '/index.html' not in paths or len(paths) > 1000:
        raise RuntimeError('Unexpected staging hosting artifact')
    session = client()
    base = 'https://firebasehosting.googleapis.com/v1beta1/'
    version = api(session, 'POST', base+f'sites/{SITE}/versions', json={'config': config})
    record['hostingVersion'] = version['name']
    save(record)
    population = api(session, 'POST', base+version['name']+':populateFiles', json={'files': paths})
    upload = population['uploadUrl']
    if not upload.startswith('https://upload-firebasehosting.googleapis.com/upload/sites/'+SITE+'/'):
        raise RuntimeError('Unexpected hosting upload destination')
    for digest in population.get('uploadRequiredHashes', []):
        response = session.post(upload+'/'+digest, data=blobs[digest],
            headers={'Content-Type': 'application/octet-stream'}, timeout=60)
        if response.status_code != 200:
            raise RuntimeError('Hosting asset upload failed: HTTP '+str(response.status_code))
    api(session, 'PATCH', base+version['name'], params={'updateMask': 'status'}, json={'status': 'FINALIZED'})
    release = api(session, 'POST', base+f'sites/{SITE}/releases', params={'versionName': version['name']}, json={
        'message': 'CookCredit isolated hiring staging; real API; payments/email/assessment bridge gated'})
    record.update(hostingRelease=release['name'], frontendUrl='https://'+SITE+'.web.app',
                  hostedFrontendBuild=record['frontendBuild'])
    save(record)
    print(json.dumps({'site': record['frontendUrl'], 'files': len(paths), 'release': release['name']}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['provision', 'configure', 'data', 'firebase', 'firebase_shared_auth', 'build', 'build_functional', 'build_status',
        'migration_job', 'migrate', 'migration_status', 'deploy_api', 'api_status', 'frontend_build', 'frontend_status',
        'host_frontend', 'build_evidence', 'probe_job', 'probe_run', 'probe_status', 'schedules', 'schedules_status', 'queue_logging',
        'webhook_receiver', 'webhook_receiver_status', 'webhook_job', 'webhook_run', 'webhook_status', 'status'])
    globals()[parser.parse_args().phase]()
