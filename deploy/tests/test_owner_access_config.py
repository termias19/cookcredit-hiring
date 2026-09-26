"""Deployment opt-ins must not silently activate mail or inbox reads."""
import importlib.util
from pathlib import Path
import pytest
spec = importlib.util.spec_from_file_location('access_deployment', Path(__file__).parents[1]/'hiring_staging.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_default_release_has_no_access_jobs_or_secrets():
    values, refs, jobs = module.owner_access_config({})
    assert values == {'HIRING_ACCESS_APPROVALS_ENABLED':'0','HIRING_ACCESS_INBOX_ENABLED':'0'}
    assert not refs and not jobs


def test_approvals_can_launch_before_mailbox_connection():
    values, refs, jobs = module.owner_access_config({'ownerAccessReviewed':True,'googleSmtpAuthenticated':True})
    assert values['HIRING_ACCESS_APPROVALS_ENABLED'] == '1'
    assert values['HIRING_ACCESS_INBOX_ENABLED'] == '0'
    assert not refs
    assert jobs == []  # Preserve the already deployed email job.


@pytest.mark.parametrize('record', [
    {'ownerAccessInboxReviewed':True},
    {'ownerAccessReviewed':True},
    {'ownerAccessReviewed':True,'googleSmtpAuthenticated':True,'ownerAccessInboxReviewed':True},
])
def test_incomplete_release_rejected(record):
    with pytest.raises(RuntimeError):
        module.owner_access_config(record)


def test_both_mailboxes_use_separate_secret_references():
    values, refs, jobs = module.owner_access_config(dict(ownerAccessReviewed=True,
        googleSmtpAuthenticated=True,ownerAccessInboxReviewed=True,ownerAccessInboxSecretsReady=True))
    assert all(value == '1' for value in values.values())
    assert set(refs) == {'HIRING_INBOX_CONTACT_APP_PASSWORD','HIRING_INBOX_OWNER_APP_PASSWORD'}
    assert len(set(refs.values())) == 2
    assert ('cc-hiring-stg-access-inbox','/api/access/internal/sync-inbox') in jobs


def test_text_true_is_not_release_authorization():
    values, refs, jobs = module.owner_access_config({'ownerAccessReviewed':'true'})
    assert values['HIRING_ACCESS_APPROVALS_ENABLED'] == '0'
    assert not refs and not jobs

@pytest.mark.parametrize('change', [None, 'disabled', 'wrong_path', 'wrong_identity', 'wrong_audience'])
def test_existing_email_schedule_validation(change):
    origin = 'https://hiring.example.test'
    job = {'state':'ENABLED','httpTarget':{'uri':origin+'/api/auth/internal/dispatch-emails',
        'httpMethod':'POST','oidcToken':{'audience':origin,
        'serviceAccountEmail':f'{module.WORKER}@{module.PROJECT}.iam.gserviceaccount.com'}}}
    import copy
    before = copy.deepcopy(job)
    module.validate_owner_email_schedule(job,origin)
    assert job == before
    if change is None:
        job = None
    elif change == 'disabled':
        job['state'] = 'PAUSED'
    elif change == 'wrong_path':
        job['httpTarget']['uri'] = origin+'/other'
    elif change == 'wrong_identity':
        job['httpTarget']['oidcToken']['serviceAccountEmail'] = 'other@example.test'
    else:
        job['httpTarget']['oidcToken']['audience'] = 'https://other.example.test'
    with pytest.raises(RuntimeError,match='existing'):
        module.validate_owner_email_schedule(job,origin)
