from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hiring_webhook_alert as alert


def test_only_production_webhook_attempts_leave_the_immediate_scheduler_rule():
    policy = {'enabled': True, 'notificationChannels': ['owner-channel'], 'conditions': [{
        'name': 'existing-condition',
        'conditionMatchedLog': {'filter': alert.SCHEDULER_FILTER, 'labelExtractors': {'job': 'EXTRACT(resource.labels.job_id)'}},
    }]}
    changed = alert.scheduler_conditions(policy)
    assert changed[0]['name'] == policy['conditions'][0]['name']
    assert changed[0]['conditionMatchedLog']['labelExtractors'] == policy['conditions'][0]['conditionMatchedLog']['labelExtractors']
    assert changed[0]['conditionMatchedLog']['filter'] == alert.SCHEDULER_FILTER + ' AND resource.labels.job_id!="cc-hiring-webhooks"'
    assert policy['conditions'][0]['conditionMatchedLog']['filter'] == alert.SCHEDULER_FILTER
    policy['conditions'] = changed
    assert alert.scheduler_conditions(policy) == changed
    policy['conditions'][0]['conditionMatchedLog']['filter'] += ' AND severity>=CRITICAL'
    with pytest.raises(RuntimeError, match='changed outside'):
        alert.scheduler_conditions(policy)


def test_cutover_requires_a_positive_sample_after_the_policy_exists():
    now = datetime(2026, 11, 9, 15, 30, tzinfo=timezone.utc)
    created = now - timedelta(minutes=8)

    def series(start, value):
        return [{'points': [{
            'interval': {'startTime': start.isoformat(), 'endTime': (start + timedelta(minutes=1)).isoformat()},
            'value': {'int64Value': str(value)},
        }]}]

    assert not alert.has_fresh_success([], created, now)
    assert not alert.has_fresh_success(series(created - timedelta(seconds=1), 1), created, now)
    assert not alert.has_fresh_success(series(created + timedelta(minutes=1), 0), created, now)
    assert not alert.has_fresh_success(series(now, 1), created, now)
    assert alert.has_fresh_success(series(created + timedelta(minutes=1), 1), created, now)


def test_changed_retry_deadline_requires_review():
    job = {'state': 'ENABLED', 'schedule': '*/5 * * * *', 'attemptDeadline': '300s',
           'retryConfig': {'retryCount': 3, 'maxRetryDuration': '0s', 'minBackoffDuration': '15s',
                           'maxBackoffDuration': '120s', 'maxDoublings': 5}}
    alert.validate_job(job)
    with pytest.raises(RuntimeError, match='retry budget'):
        alert.validate_job({**job, 'attemptDeadline': '600s'})


def test_email_monitor_reuses_rollout_without_replacing_webhook_coverage():
    settings=alert.job_settings('emails')
    assert settings['job']=='cc-hiring-emails'
    assert 'cc-hiring-webhooks' not in settings['query']
    assert settings['query'].endswith('[40m])')
    assert settings['metric']=='cookcredit_hiring_email_success'
    policy={'enabled':True,'notificationChannels':['owner-channel'],'conditions':[{
        'name':'original-condition','conditionMatchedLog':{'filter':alert.SCHEDULER_FILTER+alert.WEBHOOK_EXCLUSION}}]}
    changed=alert.scheduler_conditions(policy,'emails')
    assert changed[0]['conditionMatchedLog']['filter']==alert.SCHEDULER_FILTER+alert.WEBHOOK_EXCLUSION+' AND resource.labels.job_id!="cc-hiring-emails"'
    policy['conditions']=changed
    assert alert.scheduler_conditions(policy)==changed
    assert alert.scheduler_conditions(policy,'emails')==changed
    with pytest.raises(ValueError):alert.job_settings('expiry')


def test_email_rollout_requires_its_actual_cadence_and_retry_budget():
    job={'state':'ENABLED','schedule':'* * * * *','attemptDeadline':'300s',
         'retryConfig':{'retryCount':3,'maxRetryDuration':'0s','minBackoffDuration':'15s','maxBackoffDuration':'120s','maxDoublings':5}}
    alert.validate_job(job,'emails')
    with pytest.raises(RuntimeError):alert.validate_job({**job,'schedule':'*/5 * * * *'},'emails')


@pytest.mark.parametrize('recovered', [False, True])
def test_email_immediate_filters_change_only_after_replacement_observes_success(monkeypatch,recovered):
    import copy
    now=datetime.now(timezone.utc)
    scheduler={'name':'projects/test/alertPolicies/scheduler','displayName':'CookCredit hiring production background job failure',
        'enabled':True,'notificationChannels':['owner-channel'],'conditions':[{'name':'condition',
        'conditionMatchedLog':{'filter':alert.SCHEDULER_FILTER+alert.WEBHOOK_EXCLUSION}}]}
    delivery={'name':'projects/test/alertPolicies/delivery','displayName':'CookCredit hiring production application and delivery failures',
        'enabled':True,'notificationChannels':['owner-channel'],'conditions':[{'name':'delivery-condition',
        'conditionMatchedLog':{'filter':alert.application_error_filter('production')}}]}
    replacement={**alert.stalled_policy(['owner-channel'],'emails'),'name':'replacement',
                 'mutationRecord':{'mutateTime':(now-timedelta(minutes=5)).isoformat()}}
    settings=alert.job_settings('emails')
    patches=[]
    def api(session,method,url,**kwargs):
        if url.endswith('/jobs/cc-hiring-emails'):
            return {'state':'ENABLED','schedule':'* * * * *','attemptDeadline':'300s','retryConfig':{'retryCount':3,'maxRetryDuration':'0s','minBackoffDuration':'15s','maxBackoffDuration':'120s','maxDoublings':5}}
        if url.endswith('/alertPolicies'):return {'alertPolicies':[scheduler,delivery,replacement]}
        if url.endswith('/metrics/'+settings['metric']):return {'filter':settings['success_filter'],'metricDescriptor':{'metricKind':'DELTA','valueType':'INT64'}}
        if url.endswith('/timeSeries'):
            return {'timeSeries':[{'points':[{'interval':{'startTime':(now-timedelta(minutes=2)).isoformat(),'endTime':(now-timedelta(minutes=1)).isoformat()},'value':{'int64Value':'1'}}]}]} if recovered else {}
        current=scheduler if url.endswith('/scheduler') else delivery if url.endswith('/delivery') else None
        assert current is not None
        if method=='PATCH':
            assert kwargs['params']=={'updateMask':'conditions'}
            patches.append(current['name']);current['conditions']=copy.deepcopy(kwargs['json']['conditions'])
        else:assert method=='GET'
        return copy.deepcopy(current)
    monkeypatch.setattr(alert,'api',api)
    result=alert.run(None,'activate','emails')
    assert result['activated'] is recovered
    assert len(patches)==(2 if recovered else 0)
    if recovered:
        assert 'retryableBackground=true' in delivery['conditions'][0]['conditionMatchedLog']['filter']
        assert scheduler['notificationChannels']==delivery['notificationChannels']==['owner-channel']
