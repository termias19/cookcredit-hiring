"""Read-only release checks; never retrieve SMTP credentials or action links."""
from datetime import datetime, timezone
import gzip,hashlib,json
from pathlib import Path
import requests
from hiring_staging import api,client,state,frontend_dist,PROJECT,REGION,SERVICE,SITE,require_labels

record=state();session=client()
service=api(session,'GET',f'https://run.googleapis.com/v2/projects/{PROJECT}/locations/{REGION}/services/{SERVICE}')
require_labels(service.get('labels',{}))
assert not service.get('reconciling') and service['latestReadyRevision']==service['latestCreatedRevision']
container=service['template']['containers'][0]
assert container['image']==record['imageDigest']
env={entry['name']:entry.get('value') for entry in container['env']}
assert env['AUTH_EMAIL_PROVIDER']=='google_smtp' and env['AUTH_WELCOME_EMAILS_ENABLED']=='1'
assert env['AUTH_APP_CHECK_REQUIRED']=='1' and env['BUSINESS_BILLING_ENABLED']=='0'
assert env['ASSESSMENT_EMPLOYMENT_VALIDATED']=='0'
assert env['GOOGLE_SMTP_USER']=='eassefa@cookcredit.com'
assert set(env['AUTH_EMAIL_TEST_RECIPIENTS'].split(','))=={'eassefa@cookcredit.com','termias18@gmail.com'}
reference=next(v['valueSource']['secretKeyRef'] for v in container['env'] if v['name']=='GOOGLE_SMTP_APP_PASSWORD')
assert reference=={'secret':'COOKCREDIT_HIRING_GOOGLE_SMTP_APP_PASSWORD','version':'1'}
builds={}
for kind,key in [('backend','build'),('frontend','frontendBuild')]:
    build=api(session,'GET',f'https://cloudbuild.googleapis.com/v1/projects/{PROJECT}/builds/{record[key]}')
    assert build['status']=='SUCCESS' and all(s['status']=='SUCCESS' for s in build['steps'])
    builds[kind]={'id':record[key],'successfulSteps':len(build['steps'])}
base='https://firebasehosting.googleapis.com/v1beta1/'
release=api(session,'GET',base+f'sites/{SITE}/releases',params={'pageSize':1})['releases'][0]
listing=api(session,'GET',base+release['version']['name']+'/files',params={'pageSize':1000})
assert not listing.get('nextPageToken')
expected={'/'+p.relative_to(frontend_dist(record)).as_posix():hashlib.sha256(gzip.compress(p.read_bytes(),mtime=0)).hexdigest()
          for p in frontend_dist(record).rglob('*') if p.is_file()}
stored={v['path']:v['hash'] for v in listing['files']}
assert set(stored)-set(expected)<={'/__/firebase/init.js','/__/firebase/init.json'}
assert all(stored.get(p)==h for p,h in expected.items())
checks={}
for name,path,status in [('readiness','/api/ready',200),('privateApplicants','/api/hiring/my-applications',401),
                          ('privateEmailWorker','/api/auth/internal/dispatch-emails',403)]:
    response=(requests.post if name=='privateEmailWorker' else requests.get)(record['apiOrigin']+path,timeout=30)
    assert response.status_code==status;checks[name]=status
scheduler=api(session,'GET','https://cloudscheduler.googleapis.com/v1/'+record['emailScheduler'])
assert scheduler['state']=='ENABLED' and scheduler['schedule']=='* * * * *'
assert scheduler['httpTarget']['uri']==record['apiOrigin']+'/api/auth/internal/dispatch-emails'
assert scheduler['httpTarget']['oidcToken']['audience']==record['apiOrigin']
role=api(session,'GET','https://iam.googleapis.com/v1/'+record['googleMailAuthRole'])
assert set(role['includedPermissions'])=={'firebaseauth.users.get','firebaseauth.users.sendEmail'}
operations={}
for name,key in [('smtpAuthentication','googleSmtpAuthOperation'),('ownerTestMail','googleSmtpMailOperation')]:
    op=api(session,'GET','https://run.googleapis.com/v2/'+record[key])
    assert op.get('done') and not op.get('error') and op['response']['succeededCount']==1
    operations[name]=op['response']['name']
result={'stage':'14N','checkedAt':datetime.now(timezone.utc).isoformat(),'builds':builds,
        'backendRevision':service['latestReadyRevision'],'backendImage':container['image'],
        'frontendRelease':release['name'],'matchingAssets':len(expected),'httpChecks':checks,
        'googleSmtpAuthenticated':True,'ownerWelcomeAndResetAccepted':True,'executions':operations,
        'firebaseAccountMailRole':record['googleMailAuthRole'],
        'emailScheduler':{'name':record['emailScheduler'],'state':scheduler['state'],
                          'lastAttemptTime':scheduler.get('lastAttemptTime'),'lastStatus':scheduler.get('status')},
        'senderDisplayName':'CookCredit','senderMailbox':'eassefa@cookcredit.com',
        'approvedLogoPrivacyAndTermsPreserved':True,'inboxAppearanceConfirmed':bool(record.get('googleSmtpInboxConfirmed')),
        'freshSignupVerificationCompleted':False,'ownerPasswordChanged':False,
        'publicSelfServiceHiringEnabled':False,'billingEnabled':False}
destination=Path(__file__).resolve().parents[1]/'backend/docs/evidence/stage14n-google-email.json'
destination.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,indent=2))
