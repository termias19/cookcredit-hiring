"""Scoped Google Workspace email setup for the isolated CookCredit hiring service.

Credentials remain in Secret Manager and the runtime environment, never in this
ledger or command output. Preflight authenticates only; test_mail checks the
owner's welcome/reset requests submitted through the actual browser flows.
"""
import argparse
import base64
import json
from pathlib import Path
from hiring_staging import (api, client, state, save, grant_secret, require_labels,
                            PROJECT, REGION, SERVICE, RUNTIME, WORKER, ACCOUNT, LABELS)

SECRET = 'COOKCREDIT_HIRING_GOOGLE_SMTP_APP_PASSWORD'
AUTH_JOB = 'cc-hiring-stg-email-auth'
MAIL_JOB = 'cc-hiring-stg-email-test'

AUTH_SCRIPT = '''import os,smtplib,ssl,sys
try:
    with smtplib.SMTP('smtp.gmail.com',587,timeout=15) as smtp:
        smtp.ehlo(); smtp.starttls(context=ssl.create_default_context()); smtp.ehlo()
        smtp.login(os.environ['GOOGLE_SMTP_USER'], ''.join(os.environ['GOOGLE_SMTP_APP_PASSWORD'].split()))
    print('GOOGLE_SMTP_AUTHENTICATED')
except Exception as exc:
    print('GOOGLE_SMTP_AUTH_FAILED:'+type(exc).__name__)
    sys.exit(1)
'''

MAIL_SCRIPT = '''import json,os
assert os.environ['COOKCREDIT_ENVIRONMENT']=='staging'
assert os.environ['AUTH_EMAIL_PROVIDER']=='google_smtp'
from services.firebase import get_auth
from services.database import db_session
from services.account_email import dispatch_account_emails
from models.account_email import AccountEmail
owner=get_auth().get_user_by_email('eassefa@cookcredit.com')
assert owner.email_verified and not owner.disabled
with db_session() as session:
    kinds={r.kind for r in session.query(AccountEmail).filter(AccountEmail.recipient==owner.email).all()}
    assert {'welcome','reset'} <= kinds, 'Complete the browser requests before checking delivery'
result=dispatch_account_emails(limit=10)
with db_session() as session:
    rows=session.query(AccountEmail).filter(AccountEmail.recipient==owner.email).all()
    statuses=[{'kind':r.kind,'status':r.status,'attempts':r.attempts} for r in rows]
assert any(r['kind']=='welcome' and r['status']=='sent' for r in statuses)
assert any(r['kind']=='reset' and r['status']=='sent' for r in statuses)
print('COOKCREDIT_GOOGLE_EMAIL_PROOF:'+json.dumps({'dispatch':result,'messages':statuses}))
'''


def prepare_job(session, name, script, *, mail=False):
    service=api(session,'GET',f'https://run.googleapis.com/v2/projects/{PROJECT}/locations/{REGION}/services/{SERVICE}')
    require_labels(service.get('labels',{}))
    if service.get('reconciling'):
        raise RuntimeError('Wait for the existing service deployment')
    template=service['template']; container=template['containers'][0]
    env=[{'name':'GOOGLE_SMTP_USER','value':ACCOUNT},
         {'name':'GOOGLE_SMTP_APP_PASSWORD','valueSource':{'secretKeyRef':{'secret':SECRET,'version':'1'}}}]
    task={'serviceAccount':f'{RUNTIME}@{PROJECT}.iam.gserviceaccount.com','maxRetries':0,'timeout':'180s',
          'containers':[{'image':container['image'],'command':['python'],'args':['-c',script],
                         'env':env,'resources':{'limits':{'cpu':'1','memory':'512Mi'}}}]}
    if mail:
        assert state().get('googleSmtpAuthenticated')
        assert any(v['name']=='AUTH_EMAIL_PROVIDER' and v.get('value')=='google_smtp' for v in container['env'])
        task['volumes']=template['volumes'];task['vpcAccess']=template['vpcAccess']
        task['containers'][0].update(env=container['env'],volumeMounts=container['volumeMounts'])
    endpoint=f'https://run.googleapis.com/v2/projects/{PROJECT}/locations/{REGION}/jobs/{name}'
    current=api(session,'GET',endpoint,missing=True)
    body={'labels':LABELS,'template':{'taskCount':1,'parallelism':1,'template':task}}
    if current:
        require_labels(current.get('labels',{}))
        body.update(name=current['name'],etag=current['etag'])
        api(session,'PATCH',endpoint,json=body)
    else:
        api(session,'POST',endpoint.rsplit('/',1)[0],params={'jobId':name},json=body)
    print('Prepared '+name)


def preflight():
    session=client()
    version=api(session,'GET',f'https://secretmanager.googleapis.com/v1/projects/{PROJECT}/secrets/{SECRET}/versions/1')
    assert version['state']=='ENABLED'
    grant_secret(session,SECRET,f'{RUNTIME}@{PROJECT}.iam.gserviceaccount.com')
    prepare_job(session,AUTH_JOB,AUTH_SCRIPT)


def run_job(name,key):
    session=client();record=state()
    if record.get(key):
        raise RuntimeError('Execution already recorded; inspect status before any retry')
    endpoint=f'https://run.googleapis.com/v2/projects/{PROJECT}/locations/{REGION}/jobs/{name}'
    job=api(session,'GET',endpoint);require_labels(job.get('labels',{}))
    assert not job.get('reconciling') and job.get('terminalCondition',{}).get('state')=='CONDITION_SUCCEEDED'
    operation=api(session,'POST',endpoint+':run',json={})
    record[key]=operation['name'];save(record)
    print('Started '+name)


def auth_run():run_job(AUTH_JOB,'googleSmtpAuthOperation')


def check(key,success_key):
    session=client();record=state()
    op=api(session,'GET','https://run.googleapis.com/v2/'+record[key])
    success=bool(op.get('done') and not op.get('error') and op.get('response',{}).get('succeededCount')==1)
    if op.get('done'):
        record[success_key]=success;save(record)
    print(json.dumps({'done':op.get('done',False),'succeeded':success,'execution':op.get('response',{}).get('name')}))


def auth_status():check('googleSmtpAuthOperation','googleSmtpAuthenticated')


def auth_permissions():
    session=client();record=state()
    project=record['firebaseConfig']['projectId']
    assert project=='foodnlit-1123e' and record.get('sharedCookCreditAuth')
    name=f'projects/{project}/roles/cookcreditHiringAccountMail'
    endpoint='https://iam.googleapis.com/v1/'+name
    permissions={'firebaseauth.users.get','firebaseauth.users.sendEmail'}
    role=api(session,'GET',endpoint,missing=True)
    if role:
        assert set(role.get('includedPermissions',[]))==permissions and not role.get('deleted')
    else:
        api(session,'POST',f'https://iam.googleapis.com/v1/projects/{project}/roles',json={
            'roleId':'cookcreditHiringAccountMail','role':{'title':'CookCredit hiring account email',
            'description':'Read account status and generate verification/reset links for CookCredit hiring.',
            'includedPermissions':sorted(permissions),'stage':'GA'}})
    endpoint=f'https://cloudresourcemanager.googleapis.com/v1/projects/{project}'
    policy=api(session,'POST',endpoint+':getIamPolicy',json={'options':{'requestedPolicyVersion':3}})
    member=f'serviceAccount:{RUNTIME}@{PROJECT}.iam.gserviceaccount.com'
    binding=next((b for b in policy.get('bindings',[]) if b['role']==name and not b.get('condition')),None)
    if binding is None:
        policy.setdefault('bindings',[]).append({'role':name,'members':[member]})
    elif member not in binding.get('members',[]):
        binding.setdefault('members',[]).append(member)
    else:
        record['googleMailAuthRole']=name;save(record);return
    api(session,'POST',endpoint+':setIamPolicy',json={'policy':policy})
    record['googleMailAuthRole']=name;save(record)
    print('Granted only Firebase account lookup and account-email-link generation to the hiring runtime.')


def mail_retry():
    # A diagnosed, failed read/check execution may be retried after correction.
    # The script only checks/dispatches existing outbox rows; it never enqueues.
    session=client();record=state()
    assert record.get('googleMailAuthRole')
    previous=record['googleSmtpMailOperation']
    op=api(session,'GET','https://run.googleapis.com/v2/'+previous)
    assert op.get('done') and op.get('error') and not record.get('googleSmtpTestMailAccepted')
    record.setdefault('googleSmtpMailPriorOperations',[]).append(previous)
    del record['googleSmtpMailOperation'];save(record)
    run_job(MAIL_JOB,'googleSmtpMailOperation')


def test_mail():
    if state().get('googleSmtpMailOperation'):
        raise RuntimeError('Owner test mail was already requested; inspect it, do not resend blindly')
    prepare_job(client(),MAIL_JOB,MAIL_SCRIPT,mail=True)


def mail_run():run_job(MAIL_JOB,'googleSmtpMailOperation')
def mail_status():check('googleSmtpMailOperation','googleSmtpTestMailAccepted')


def scheduler():
    session=client();record=state();assert record.get('googleSmtpAuthenticated')
    name=f'projects/{PROJECT}/locations/{REGION}/jobs/cc-hiring-stg-emails'
    endpoint='https://cloudscheduler.googleapis.com/v1/'+name
    current=api(session,'GET',endpoint,missing=True)
    description='CookCredit isolated hiring account email outbox'
    body={'name':name,'description':description,'schedule':'* * * * *','timeZone':'Etc/UTC',
          'attemptDeadline':'300s','retryConfig':{'retryCount':0},
          'httpTarget':{'uri':record['apiOrigin']+'/api/auth/internal/dispatch-emails','httpMethod':'POST',
                        'headers':{'Content-Type':'application/json'},'body':base64.b64encode(b'{}').decode(),
                        'oidcToken':{'serviceAccountEmail':f'{WORKER}@{PROJECT}.iam.gserviceaccount.com',
                                     'audience':record['apiOrigin']}}}
    if current:
        assert current.get('description')==description
        api(session,'PATCH',endpoint,params={'updateMask':'schedule,timeZone,attemptDeadline,retryConfig,httpTarget'},json=body)
    else:
        api(session,'POST',endpoint.rsplit('/',1)[0],json=body)
    record['emailScheduler']=name;save(record)
    print('Configured authenticated email dispatch every minute; outbox owns retries.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase',choices=['preflight','auth_run','auth_status','auth_permissions','test_mail','mail_run','mail_retry','mail_status','scheduler'])
    globals()[parser.parse_args().phase]()
