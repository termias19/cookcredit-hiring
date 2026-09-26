"""One recorded reset of the isolated hiring staging database after backup.

Does not touch Firebase identities, live assessment storage, or another database.
The reset job checks the reviewed table counts and user IDs inside its transaction.
"""
import argparse,copy,json,hashlib,re
from pathlib import Path
from urllib.parse import quote
from hiring_staging import client,api,require_labels,PROJECT,REGION,SQL,BUCKET,QUEUE,LABELS,MIGRATOR

WORK=Path(__file__).resolve().parents[2]/'work'
FILE=WORK/'hiring-clean-start.json'
JOB='cc-hiring-stg-clean-start'


def save(record): FILE.write_text(json.dumps(record,indent=2),encoding='utf-8')
def read(): return json.loads(FILE.read_text())


def prepare():
    session=client(); reviewed=json.loads((WORK/'launch-operations.json').read_text())
    assert reviewed.get('backupId'), 'Successful backup required'
    endpoint=f'https://sqladmin.googleapis.com/sql/v1beta4/projects/{PROJECT}/instances/{SQL}'
    database=api(session,'GET',endpoint);require_labels(database['settings'].get('userLabels',{}))
    backup=api(session,'GET',endpoint+'/backupRuns/'+reviewed['backupId'])
    assert backup['status']=='SUCCESSFUL' and backup['instance']==SQL
    inventory=reviewed['databaseInventory']; users=inventory['users']
    assert all(u['email'] in ('eassefa@cookcredit.com','termias18@gmail.com') or
               (u['email'].endswith('@example.test') and u['id'].startswith(('staging-hook-','staging-probe-','sustained-'))) for u in users), 'Unrecognized account: review before deletion'
    assert inventory['tables']['hiring_applications']==inventory['tables']['skill_attempts']==inventory['tables']['stripe_events']==0
    tables=sorted(set(inventory['tables'])-{'schema_migrations','spatial_ref_sys'})
    objects=api(session,'GET',f'https://storage.googleapis.com/storage/v1/b/{BUCKET}/o',params={'maxResults':1000})
    assert not objects.get('nextPageToken')
    media=[{'name':x['name'],'generation':x['generation'],'size':x['size']} for x in objects.get('items',[])]
    record={'database':'cookcredit_hiring_staging','instance':SQL,'backupId':reviewed['backupId'],
            'tables':tables,'reviewedCounts':inventory['tables'],'reviewedUserIds':sorted(u['id'] for u in users),
            'media':media,'resetSucceeded':False,'schedulersPaused':[]}
    save(record)
    print(json.dumps({'backupId':record['backupId'],'applicationTables':len(tables),
                      'accountsToReset':len(users),'preservedTables':['schema_migrations','spatial_ref_sys'],'media':media},indent=2))


def pause_and_prepare_job():
    record=read(); assert not record.get('resetOperation')
    session=client()
    scheduler_base=f'https://cloudscheduler.googleapis.com/v1/projects/{PROJECT}/locations/{REGION}/jobs/'
    for name in ('cc-hiring-stg-dispatch','cc-hiring-stg-webhooks','cc-hiring-stg-expiry'):
        job=api(session,'GET',scheduler_base+name)
        assert job['description']=='CookCredit isolated hiring staging recovery'
        if job['state']=='ENABLED':
            api(session,'POST',scheduler_base+name+':pause',json={})
            record['schedulersPaused'].append(name);save(record)
    queue=f'https://cloudtasks.googleapis.com/v2/projects/{PROJECT}/locations/{REGION}/queues/{QUEUE}'
    info=api(session,'GET',queue)
    if info['state']=='RUNNING':
        api(session,'POST',queue+':pause',json={});record['queuePaused']=True;save(record)
    tasks=api(session,'GET',queue+'/tasks',params={'pageSize':1000})
    assert not tasks.get('nextPageToken')
    record['queuedTasks']=len(tasks.get('tasks',[]));save(record)
    # The reviewed database has no attempts or submitted applications. Any new
    # task indicates changed activity and stops this reset rather than purging it.
    assert record['queuedTasks']==0, 'Review unexpected queued work before reset'
    migration=api(session,'GET',f'https://run.googleapis.com/v2/projects/{PROJECT}/locations/{REGION}/jobs/{MIGRATOR}')
    require_labels(migration.get('labels',{}))
    template=copy.deepcopy(migration['template'])
    container=template['template']['containers'][0]
    assert template['template']['serviceAccount']==f'{MIGRATOR}@{PROJECT}.iam.gserviceaccount.com'
    container['env']=[v for v in container['env'] if v['name']!='RUNTIME_DB_PASS']
    script='''
import json,os
from sqlalchemy import create_engine,text,inspect
from services.database import _build_url
assert os.environ['COOKCREDIT_ENVIRONMENT']=='staging'
assert os.environ['CLOUD_SQL_CONNECTION']=='cookcredit-scoring:us-central1:cookcredit-hiring-stg-db'
assert os.environ['DB_NAME']=='cookcredit_hiring_staging' and os.environ['DB_USER']=='postgres'
review=REVIEW
engine=create_engine(_build_url(),pool_size=1,max_overflow=0)
with engine.begin() as c:
 c.execute(text("SET LOCAL lock_timeout='15s'"))
 c.execute(text("SET LOCAL statement_timeout='90s'"))
 tables=sorted(set(inspect(c).get_table_names(schema='public'))-{'schema_migrations','spatial_ref_sys'})
 assert tables==review['tables'], 'Schema changed after review'
 quoted=', '.join('public."'+t.replace('"','""')+'"' for t in tables)
 c.execute(text('LOCK TABLE '+quoted+' IN ACCESS EXCLUSIVE MODE'))
 counts={t:c.execute(text('SELECT count(*) FROM public."'+t+'"')).scalar_one() for t in tables}
 assert counts=={t:review['reviewedCounts'][t] for t in tables}, 'Data changed after review'
 ids=sorted(c.execute(text('SELECT id FROM users')).scalars())
 assert ids==review['reviewedUserIds'], 'Account set changed after review'
 c.execute(text('TRUNCATE TABLE '+quoted+' RESTART IDENTITY RESTRICT'))
 assert all(c.execute(text('SELECT count(*) FROM public."'+t+'"')).scalar_one()==0 for t in tables)
 assert c.execute(text('SELECT count(*) FROM schema_migrations')).scalar_one()==27
 assert c.execute(text('SELECT count(*) FROM spatial_ref_sys')).scalar_one()==8500
print('COOKCREDIT_CLEAN_START='+json.dumps({'clearedTables':len(tables),'remainingApplicationRows':0,'preservedMigrations':27,'firebaseIdentitiesUntouched':True}),flush=True)
'''.replace('REVIEW',repr({k:record[k] for k in ('tables','reviewedCounts','reviewedUserIds')}))
    container.update(command=['python'],args=['-c',script])
    endpoint=f'https://run.googleapis.com/v2/projects/{PROJECT}/locations/{REGION}/jobs/{JOB}'
    existing=api(session,'GET',endpoint,missing=True)
    body={'labels':LABELS,'template':template}
    if existing:
        require_labels(existing.get('labels',{}));body.update(name=existing['name'],etag=existing['etag'])
        api(session,'PATCH',endpoint,json=body)
    else: api(session,'POST',endpoint.rsplit('/',1)[0],params={'jobId':JOB},json=body)
    print('Paused isolated workers and prepared the transactionally guarded reset job.')


def run():
    record=read();assert not record.get('resetOperation'), 'Reset already requested'
    session=client();endpoint=f'https://run.googleapis.com/v2/projects/{PROJECT}/locations/{REGION}/jobs/{JOB}'
    job=api(session,'GET',endpoint);require_labels(job.get('labels',{}));assert not job.get('reconciling')
    op=api(session,'POST',endpoint+':run',json={});record['resetOperation']=op['name'];save(record)
    print('Started the approved isolated hiring test-data reset.')


def status():
    record=read();result=api(client(),'GET','https://run.googleapis.com/v2/'+record['resetOperation'])
    record['resetSucceeded']=bool(result.get('done') and not result.get('error') and result.get('response',{}).get('succeededCount')==1)
    record['execution']=result.get('response',{}).get('name');save(record)
    print(json.dumps({'done':result.get('done'),'success':record['resetSucceeded'],'execution':record['execution'],'error':result.get('error')}))


def resume():
    record=read();session=client()
    # Always usable for recovery, including a failed reset. No new schedules.
    for name in record.get('schedulersPaused',[]):
        endpoint=f'https://cloudscheduler.googleapis.com/v1/projects/{PROJECT}/locations/{REGION}/jobs/{name}'
        current=api(session,'GET',endpoint)
        assert current['description']=='CookCredit isolated hiring staging recovery'
        if current['state']=='PAUSED':api(session,'POST',endpoint+':resume',json={})
    if record.get('queuePaused'):
        endpoint=f'https://cloudtasks.googleapis.com/v2/projects/{PROJECT}/locations/{REGION}/queues/{QUEUE}'
        if api(session,'GET',endpoint)['state']=='PAUSED':api(session,'POST',endpoint+':resume',json={})
    record['workersResumed']=True;save(record);print('Restored the dedicated hiring schedules and queue.')


def media():
    record=read(); assert record['resetSucceeded']
    session=client(); backup=WORK/'hiring-reset-media-backup';backup.mkdir(exist_ok=True)
    removed=[]
    for item in record['media']:
        name=item['name']
        assert re.fullmatch(r'company_branding/[0-9a-f-]{36}/[0-9a-f]{64}\.png',name), 'Unexpected media: review before deletion'
        endpoint=f'https://storage.googleapis.com/storage/v1/b/{BUCKET}/o/'+quote(name,safe='')
        response=session.get(endpoint,params={'alt':'media','generation':item['generation']},timeout=30)
        response.raise_for_status();assert len(response.content)==int(item['size'])
        path=backup/(hashlib.sha256(name.encode()).hexdigest()+'.png');path.write_bytes(response.content)
        assert path.read_bytes()==response.content
        api(session,'DELETE',endpoint,params={'ifGenerationMatch':item['generation']})
        removed.append({'name':name,'generation':item['generation'],'backup':str(path),'sha256':hashlib.sha256(response.content).hexdigest()})
    record['removedTestMedia']=removed;save(record);print('Backed up and removed '+str(len(removed))+' isolated test logo object(s).')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('phase',choices=['prepare','pause_and_prepare_job','run','status','resume','media'])
    globals()[p.parse_args().phase]()
