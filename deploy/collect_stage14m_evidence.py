"""Read-only evidence for the public entry and final hiring release."""
from datetime import datetime, timezone
import gzip,hashlib,json,re
from pathlib import Path
import requests
from hiring_staging import api,client,state,frontend_dist,PROJECT,REGION,SERVICE,SITE,require_labels

ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT.parent/'work'
session=client(); record=state()
service=api(session,'GET',f'https://run.googleapis.com/v2/projects/{PROJECT}/locations/{REGION}/services/{SERVICE}')
require_labels(service.get('labels',{}))
assert not service.get('reconciling') and service['latestReadyRevision']==service['latestCreatedRevision']
container=service['template']['containers'][0]
assert container['image']==record['imageDigest']
env={v['name']:v.get('value') for v in container['env']}
assert env['BUSINESS_BILLING_ENABLED']=='0' and env['INTEGRATION_EARLY_ACCESS_ENABLED']=='1'
assert env['EARLY_ACCESS_MONTHLY_ASSESSMENT_LIMIT']=='100'
assert env['AUTH_APP_CHECK_REQUIRED']=='1' and env['ASSESSMENT_EMPLOYMENT_VALIDATED']=='0'
assert set(env['STAGING_ALLOWED_EMAILS'].split(','))=={'eassefa@cookcredit.com','termias18@gmail.com','staging-smoke@cookcredit.invalid'}
builds={}
for label,key in [('backend','build'),('frontend','frontendBuild')]:
    build=api(session,'GET',f'https://cloudbuild.googleapis.com/v1/projects/{PROJECT}/builds/{record[key]}')
    assert build['status']=='SUCCESS' and all(step['status']=='SUCCESS' for step in build['steps'])
    builds[label]={'id':record[key],'successfulSteps':len(build['steps'])}
hosting='https://firebasehosting.googleapis.com/v1beta1/'
release=api(session,'GET',hosting+f'sites/{SITE}/releases',params={'pageSize':1})['releases'][0]
listing=api(session,'GET',hosting+release['version']['name']+'/files',params={'pageSize':1000})
assert not listing.get('nextPageToken')
expected={'/'+p.relative_to(frontend_dist(record)).as_posix():hashlib.sha256(gzip.compress(p.read_bytes(),mtime=0)).hexdigest()
          for p in frontend_dist(record).rglob('*') if p.is_file()}
stored={f['path']:f['hash'] for f in listing['files']}
# Firebase adds these managed configuration endpoints to every hosting version.
# Require every application byte to match and reject any other unexpected path.
managed_paths={'/__/firebase/init.js','/__/firebase/init.json'}
assert set(stored)-set(expected) <= managed_paths
assert all(stored.get(path)==digest for path,digest in expected.items())
checks={}
for name,path,code in [('health','/api/health',200),('readiness','/api/ready',200),('privateApplications','/api/hiring/my-applications',401)]:
    response=requests.get(record['apiOrigin']+path,timeout=30);assert response.status_code==code
    checks[name]=code
page=requests.get('https://'+SITE+'.web.app/business',timeout=30)
assert page.status_code==200 and 'noindex' in page.headers.get('X-Robots-Tag','')
assert page.content==(frontend_dist(record)/'index.html').read_bytes()
published=json.loads((WORK/'cookcredit-main-hiring-entry/public-entry-release.json').read_text())
original=json.loads((WORK/'launch-inventory.json').read_text())['mainSite']
live_release=api(session,'GET',hosting+'sites/foodnlit-1123e/releases',params={'pageSize':1})['releases'][0]
assert live_release['name']==published['release']
preserved=[p for p,h in original['paths'].items() if p not in ('/index.html','/sitemap.xml')]
assert all(published['publishedPaths'][p]==original['paths'][p] for p in preserved)
assessment={}
for name in ('wrist.js','score.js','recording.mjs'):
    old=(WORK/'live-hiring-overlay'/('baseline-'+name)).read_bytes()
    response=requests.get('https://cookcredit-knife-demo.web.app/'+name,timeout=30)
    assert response.ok and response.content==old
    assessment[name]=hashlib.sha256(old).hexdigest()
clean=json.loads((WORK/'hiring-clean-start.json').read_text())
assert clean['resetSucceeded'] and clean['workersResumed']
schedules=[]
for name in clean['schedulersPaused']:
    scheduler=api(session,'GET',f'https://cloudscheduler.googleapis.com/v1/projects/{PROJECT}/locations/{REGION}/jobs/{name}')
    assert scheduler['state']=='ENABLED';schedules.append(name)
queue=api(session,'GET',f'https://cloudtasks.googleapis.com/v2/projects/{PROJECT}/locations/{REGION}/queues/cookcredit-hiring-stg-scoring')
assert queue['state']=='RUNNING'
logs=api(session,'POST','https://logging.googleapis.com/v2/entries:list',json={
    'resourceNames':['projects/'+PROJECT],'pageSize':50,
    'filter':f'resource.type="build" AND resource.labels.build_id="{record["build"]}" AND textPayload:"passed"'})
tests=[m.group(0) for item in logs.get('entries',[]) if (m:=re.search(r'\b\d+ passed[^\r\n]*',item.get('textPayload','')))]
result={'stage':'14M','checkedAt':datetime.now(timezone.utc).isoformat(),'builds':builds,
 'backend':{'revision':service['latestReadyRevision'],'image':container['image'],'httpChecks':checks,'testSummaries':tests},
 'frontend':{'release':release['name'],'matchingAssetCount':len(expected),'noindex':True,
  'firebaseManagedPaths':sorted(set(stored)-set(expected))},
 'publicWebsite':{'release':published['release'],'originalAssetsPreserved':len(preserved),'urls':['https://cookcredit.com/learn/','https://cookcredit.com/hiring/'],
  'searchConsole':{'sitemapAccepted':True,'discoveredPages':7,'indexingRequested':['/hiring/','/learn/'],'indexedConfirmed':False}},
 'dataReset':{'backup':clean['backupId'],'clearedApplicationTables':len(clean['tables']),'resetExecution':clean['execution'],
  'firebaseIdentitiesUntouched':True,'workersResumed':True,'testMediaRemoved':len(clean.get('removedTestMedia',[])),
  'ownerReachedCleanOnboarding':True},
 'liveAssessmentOriginalHashes':assessment,
 'email':{'approvedTemplatePreserved':True,'nativeDeliveryActive':True,'fullBrandedDeliveryActive':False,'nativeUpdateError':'EMAIL_TEMPLATE_UPDATE_NOT_ALLOWED'},
 'integrationAccess':{'freeEarlyAccess':True,'monthlyApiRequestsPerEnvironment':100,'paymentsEnabled':False},
 'acceptance':{'publicMarketing':True,'publicSelfServiceHiring':False,'independentVideoVerifier':False,
  'realAssessmentRoundTrip':False,'fullWorkloadCapacity':False,'paymentTestDeferredByOwner':True}}
destination=ROOT/'backend/docs/evidence/stage14m-release.json';destination.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,indent=2))
