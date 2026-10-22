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
