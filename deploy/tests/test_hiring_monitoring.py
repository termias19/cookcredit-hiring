import copy
import importlib.util
from pathlib import Path
import sys
import pytest

DEPLOY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DEPLOY))
spec = importlib.util.spec_from_file_location('hiring_monitoring_test', DEPLOY / 'hiring_monitoring.py')
module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_existing_alert_is_extended_without_changing_owner_channel_or_rate():
    before = {'name': 'existing-policy', 'enabled': True, 'notificationChannels': ['owner-channel'],
              'alertStrategy': {'notificationRateLimit': {'period': '3600s'}},
              'conditions': [{'name': 'existing-condition', 'conditionMatchedLog': {'filter': 'old'}}]}
    snapshot = copy.deepcopy(before)
    after = module.desired_policy(before, 'production')
    assert before == snapshot
    assert after['name'] == before['name']
    assert after['notificationChannels'] == before['notificationChannels']
    assert after['alertStrategy'] == before['alertStrategy']
    assert 'cookcredit-hiring"' in after['conditions'][0]['conditionMatchedLog']['filter']
    assert 'jsonPayload.event:*' in after['conditions'][0]['conditionMatchedLog']['filter']
    assert '-staging' not in after['conditions'][0]['conditionMatchedLog']['filter']


def test_no_implicit_environment_or_silent_disabled_policy():
    with pytest.raises(ValueError):module.application_error_filter('other')
    with pytest.raises(RuntimeError):module.desired_policy({'conditions': []}, 'staging')
    with pytest.raises(RuntimeError):module.desired_policy({'conditions': [{'conditionMatchedLog': {}}]}, 'production')


def test_job_coverage_preserves_preexisting_email_recovery_exclusion():
    before = {'enabled': True, 'notificationChannels': ['owner-channel'], 'conditions': [
        {'conditionMatchedLog': {'filter': module.legacy_service_filter('production') + module.RECOVERY_EXCLUSION}}]}
    query = module.desired_policy(before, 'production')['conditions'][0]['conditionMatchedLog']['filter']
    assert 'resource.type="cloud_run_job"' in query
    assert 'resource.labels.job_name="cc-hiring-compression"' in query
    assert query.endswith(module.RECOVERY_EXCLUSION)


def test_recovery_aware_filter_is_narrow_and_survives_a_later_monitoring_update():
    query=module.application_error_filter('production',recoverable_background=True)
    assert query.startswith(module.application_error_filter('production')+' AND NOT (')
    assert 'jsonPayload.retryableBackground=true' in query
    assert 'jsonPayload.endpoint="auth.dispatch_emails"' in query
    assert '"dependency_unavailable" OR "request_failed"' in query
    before={'enabled':True,'notificationChannels':['owner-channel'],'conditions':[{'conditionMatchedLog':{'filter':query}}]}
    assert module.desired_policy(before,'production')['conditions'][0]['conditionMatchedLog']['filter']==query
    with pytest.raises(ValueError):module.application_error_filter('staging',recoverable_background=True)


def test_missing_staging_coverage_reuses_known_routing_without_production_identity():
    production = {'displayName': 'CookCredit hiring production application and delivery failures',
                  'enabled': True, 'combiner': 'OR', 'userLabels': {'environment': 'production'},
                  'notificationChannels': ['production-owner'],
                  'alertStrategy': {'notificationRateLimit': {'period': '3600s'}},
                  'conditions': [{'name': 'production-condition', 'conditionMatchedLog': {'filter': 'old'}}]}
    routing = {'displayName': 'CookCredit hiring staging background job failure',
               'notificationChannels': ['staging-owner']}
    result = module.missing_staging_policy([production, routing])
    assert 'name' not in result and 'name' not in result['conditions'][0]
    assert result['notificationChannels'] == ['staging-owner']
    assert result['userLabels']['environment'] == 'staging'
    assert 'cookcredit-hiring-staging' in result['conditions'][0]['conditionMatchedLog']['filter']
