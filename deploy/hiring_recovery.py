"""Restore only a hiring-staging backup into a separate, labelled drill instance."""
import argparse
import json
from pathlib import Path
from datetime import datetime, timezone
from hiring_staging import client, api, require_labels, PROJECT, REGION, SQL, LABELS, STATE_FILE, SERVICE

TARGET = 'cookcredit-hiring-stg-recovery'
FILE = STATE_FILE.with_name('hiring-recovery-state.json')
BASE = f'https://sqladmin.googleapis.com/sql/v1beta4/projects/{PROJECT}/instances'
JOB = 'cc-hiring-stg-recovery'


def read():
    return json.loads(FILE.read_text()) if FILE.exists() else {}


def save(record):
    FILE.write_text(json.dumps(record, indent=2))


def prepare():
    session, record = client(), read()
    source = api(session, 'GET', BASE+'/'+SQL)
    require_labels(source['settings'].get('userLabels', {}))
    backups = api(session, 'GET', BASE+'/'+SQL+'/backupRuns').get('items', [])
    matches = [b for b in backups if b.get('status') == 'SUCCESSFUL'
               and b.get('description') == 'CookCredit-hiring-staging-recovery-drill-20260918']
    if len(matches) != 1:
        raise RuntimeError('Expected one successful explicitly named staging drill backup')
    target = api(session, 'GET', BASE+'/'+TARGET, missing=True)
    if target:
        require_labels(target['settings'].get('userLabels', {}))
        if target['settings']['userLabels'].get('purpose') != 'restore-drill':
            raise RuntimeError('Refusing an unrelated database')
    else:
        operation = api(session, 'POST', BASE, json={'name': TARGET, 'region': REGION,
            'databaseVersion': 'POSTGRES_16', 'settings': {'tier': 'db-g1-small', 'edition': 'ENTERPRISE',
                'availabilityType': 'ZONAL', 'activationPolicy': 'ALWAYS', 'dataDiskSizeGb': '10',
                'dataDiskType': 'PD_SSD', 'storageAutoResize': True,
                'userLabels': {**LABELS, 'purpose': 'restore-drill'},
                'ipConfiguration': {'ipv4Enabled': True, 'authorizedNetworks': [], 'sslMode': 'ENCRYPTED_ONLY'}}})
        record['createOperation'] = operation['name']
    record.update(source=SQL, target=TARGET, backupId=matches[0]['id'], preparedAt=datetime.now(timezone.utc).isoformat())
    save(record)
    print(json.dumps(record))


def restore():
    session, record = client(), read()
    assert record['source'] == SQL and record['target'] == TARGET and TARGET != SQL
    current = api(session, 'GET', BASE+'/'+TARGET)
    require_labels(current['settings'].get('userLabels', {}))
    assert current['settings']['userLabels'].get('purpose') == 'restore-drill'
    if current['state'] != 'RUNNABLE':
        raise RuntimeError('Recovery target is not runnable yet')
    if record.get('restoreOperation'):
        raise RuntimeError('Restore already requested; inspect its status instead of repeating')
    operation = api(session, 'POST', BASE+'/'+TARGET+'/restoreBackup', json={'restoreBackupContext': {
        'backupRunId': record['backupId'], 'instanceId': SQL, 'project': PROJECT}})
    record['restoreOperation'] = operation['name']; save(record)
    print('Started restore into '+TARGET+' only.')


def status():
    session, record = client(), read()
    report = {}
    for key in ('createOperation', 'restoreOperation', 'stopOperation'):
        if record.get(key):
            result = api(session, 'GET', f'https://sqladmin.googleapis.com/sql/v1beta4/projects/{PROJECT}/operations/'+record[key])
            report[key] = {'status': result['status'], 'errors': result.get('error', {}).get('errors', [])}
    print(json.dumps(report))


def probe():
    session, record = client(), read()
    operation = api(session, 'GET', f'https://sqladmin.googleapis.com/sql/v1beta4/projects/{PROJECT}/operations/'+record['restoreOperation'])
    if operation['status'] != 'DONE' or operation.get('error'):
        raise RuntimeError('Restore must succeed before verification')
    service = api(session, 'GET', f'https://run.googleapis.com/v2/projects/{PROJECT}/locations/{REGION}/services/{SERVICE}')
    require_labels(service.get('labels', {}))
    template, connection = service['template'], f'{PROJECT}:{REGION}:{TARGET}'
    source = template['containers'][0]
    # Keep only database settings and the existing runtime password reference.
    names = {'COOKCREDIT_ENVIRONMENT', 'DB_NAME', 'DB_USER', 'DB_PASS', 'DB_POOL_SIZE', 'DB_MAX_OVERFLOW'}
    env = [v for v in source['env'] if v['name'] in names]
    env.append({'name': 'CLOUD_SQL_CONNECTION', 'value': connection})
    script = """
import hashlib,json,os
from sqlalchemy import create_engine,text
from services.database import _build_url
assert os.environ['CLOUD_SQL_CONNECTION'] == 'cookcredit-scoring:us-central1:cookcredit-hiring-stg-recovery'
assert os.environ['DB_USER'] == 'hiring_runtime' and os.environ['DB_NAME'] == 'cookcredit_hiring_staging'
report = {'restoredInstance': 'cookcredit-hiring-stg-recovery', 'backupReadable': True, 'tables': {}}
for label, connection in [('restored', 'cookcredit-scoring:us-central1:cookcredit-hiring-stg-recovery'), ('source', 'cookcredit-scoring:us-central1:cookcredit-hiring-stg-db')]:
    os.environ['CLOUD_SQL_CONNECTION'] = connection
    engine = create_engine(_build_url(), pool_size=1, max_overflow=0)
    with engine.connect() as db:
        db.execute(text('SET TRANSACTION READ ONLY'))
        migrations = db.execute(text('SELECT count(*) FROM schema_migrations')).scalar_one()
        assert migrations == 27
        assert not db.execute(text("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")).scalar_one()
        assert not db.execute(text("SELECT has_table_privilege(current_user, 'schema_migrations', 'INSERT')")).scalar_one()
        report[label] = {'migrations': migrations, 'runtimePrivilegesRestricted': True}
        for table in ('users', 'orgs'):
            ids = [str(row[0]) for row in db.execute(text('SELECT id FROM '+table+' ORDER BY id'))]
            report['tables'].setdefault(table, {})[label] = {'rows': len(ids), 'idDigest': hashlib.sha256(json.dumps(ids).encode()).hexdigest()}
    engine.dispose()
for table in report['tables'].values():
    assert table['restored'] == table['source'], 'Restore data does not match source'
report['sourceMatchesRestored'] = True
print('COOKCREDIT_RECOVERY='+json.dumps(report), flush=True)
"""
    endpoint = f'https://run.googleapis.com/v2/projects/{PROJECT}/locations/{REGION}/jobs/{JOB}'
    current = api(session, 'GET', endpoint, missing=True)
    body = {'labels': LABELS, 'template': {'taskCount': 1, 'parallelism': 1, 'template': {
        'serviceAccount': template['serviceAccount'], 'maxRetries': 0, 'timeout': '300s',
        'volumes': [{'name': 'cloudsql', 'cloudSqlInstance': {'instances': [connection, f'{PROJECT}:{REGION}:{SQL}']}}],
        'containers': [{'image': source['image'], 'env': env, 'command': ['python'], 'args': ['-c', script],
            'volumeMounts': [{'name': 'cloudsql', 'mountPath': '/cloudsql'}],
            'resources': {'limits': {'cpu': '1', 'memory': '512Mi'}}}]}}}
    if current:
        require_labels(current.get('labels', {})); body.update(name=current['name'], etag=current['etag'])
        api(session, 'PATCH', endpoint, json=body)
    else:
        api(session, 'POST', endpoint.rsplit('/', 1)[0], params={'jobId': JOB}, json=body)
    print('Prepared read-only source/restored comparison job.')


def run():
    session, record = client(), read()
    endpoint = f'https://run.googleapis.com/v2/projects/{PROJECT}/locations/{REGION}/jobs/{JOB}'
    job = api(session, 'GET', endpoint); require_labels(job.get('labels', {}))
    if job.get('reconciling'):
        raise RuntimeError('Job is provisioning')
    result = api(session, 'POST', endpoint+':run', json={})
    record['probeOperation'] = result['name']; save(record)
    print('Started read-only restore verification.')


def result():
    session, record = client(), read()
    operation = api(session, 'GET', 'https://run.googleapis.com/v2/'+record['probeOperation'])
    success = bool(operation.get('done') and not operation.get('error') and operation.get('response', {}).get('succeededCount') == 1)
    record['verified'] = success; save(record)
    print(json.dumps({'done': operation.get('done', False), 'verified': success,
        'execution': operation.get('response', {}).get('name'), 'error': operation.get('error', {}).get('message')}))


def stop():
    session, record = client(), read()
    target = api(session, 'GET', BASE+'/'+TARGET)
    require_labels(target['settings'].get('userLabels', {}))
    assert target['settings']['userLabels'].get('purpose') == 'restore-drill'
    operation = api(session, 'PATCH', BASE+'/'+TARGET, json={'settings': {'activationPolicy': 'NEVER'}})
    record['stopOperation'] = operation['name']; save(record)
    print('Stopped the dedicated recovery drill compute; backup and evidence retained.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['prepare', 'restore', 'status', 'probe', 'run', 'result', 'stop'])
    globals()[parser.parse_args().phase]()
