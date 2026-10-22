"""Update an existing Hiring error alert; create missing staging coverage only by opt-in."""
import argparse
import copy
import json
from hiring_staging import api, client, PROJECT


def application_error_filter(environment):
    if environment not in ('production', 'staging'):
        raise ValueError('Unknown environment')
    service = 'cookcredit-hiring' + ('-staging' if environment == 'staging' else '')
    # Structured events already exclude raw user/provider payloads. This includes
    # new failure categories automatically and works below the API-volume floor.
    return ('resource.type="cloud_run_revision" AND resource.labels.service_name="'
            + service + '" AND jsonPayload.event:* AND severity>=ERROR')


def desired_policy(current, environment):
    policy = copy.deepcopy(current)
    conditions = policy.get('conditions', [])
    if len(conditions) != 1 or 'conditionMatchedLog' not in conditions[0]:
        raise RuntimeError('Refusing to replace a different alert type')
    if not policy.get('notificationChannels') or not policy.get('enabled'):
        raise RuntimeError('Existing alert must be enabled and have its owner channel')
    policy['displayName'] = 'CookCredit hiring ' + environment + ' application and delivery failures'
    conditions[0]['displayName'] = 'Structured Hiring error, including low-traffic and browser failures'
    conditions[0]['conditionMatchedLog']['filter'] = application_error_filter(environment)
    policy['documentation'] = {'mimeType': 'text/markdown', 'content':
        'A Hiring application, browser, dependency, public-site or delivery error was recorded. '
        'Inspect the event category, requestId/clientReference, revision and source commit in Cloud Logging. '
        'Browser reports are untrusted and contain no raw error text. Review durable pending/failed '
        'records and recent successful retries before recovery. Never blindly resend applicant messages '
        'or payment events. Follow OPERATIONS.md in the public cookcredit-hiring repository.'}
    return policy


def missing_staging_policy(policies):
    # Staging has no delivery-log policy in the original deployment. Copy the
    # production log-alert shape and the staging Scheduler's existing owner channel.
    production = [p for p in policies if p.get('displayName') in {
        'CookCredit hiring production stalled or failed delivery',
        'CookCredit hiring production application and delivery failures'}]
    routing = [p for p in policies if p.get('displayName') == 'CookCredit hiring staging background job failure']
    if len(production) != 1 or len(routing) != 1 or not routing[0].get('notificationChannels'):
        raise RuntimeError('Missing reviewed Hiring alert or staging owner channel')
    seed = {key: copy.deepcopy(production[0][key]) for key in
            ('enabled', 'combiner', 'alertStrategy', 'conditions', 'userLabels') if key in production[0]}
    seed['notificationChannels'] = routing[0]['notificationChannels']
    for condition in seed['conditions']:condition.pop('name', None)
    labels = seed.get('userLabels', {})
    if 'environment' in labels:labels['environment'] = 'staging'
    return desired_policy(seed, 'staging')


def run(environment, apply=False, create_missing=False):
    session = client()
    base = 'https://monitoring.googleapis.com/v3/'
    data = api(session, 'GET', base + 'projects/' + PROJECT + '/alertPolicies')
    if data.get('nextPageToken'):
        raise RuntimeError('Policy listing truncated; inspect before updating')
    names = {'CookCredit hiring ' + environment + ' stalled or failed delivery',
             'CookCredit hiring ' + environment + ' application and delivery failures'}
    found = [row for row in data.get('alertPolicies', []) if row.get('displayName') in names]
    if not found and environment == 'staging' and create_missing:
        after = missing_staging_policy(data.get('alertPolicies', []))
        if apply:
            created = api(session, 'POST', base + 'projects/' + PROJECT + '/alertPolicies', json=after)
            assert created['notificationChannels'] == after['notificationChannels']
            return {'environment': environment, 'policy': created['name'], 'updated': True,
                    'createdMissingCoverage': True, 'filter': application_error_filter(environment)}
        return {'environment': environment, 'updated': False, 'wouldCreateMissingCoverage': True,
                'filter': application_error_filter(environment)}
    if len(found) != 1:
        raise RuntimeError('Expected one existing Hiring error policy')
    before = found[0]
    after = desired_policy(before, environment)
    if apply:
        body = {key: after[key] for key in ('name', 'displayName', 'conditions', 'documentation')}
        api(session, 'PATCH', base + after['name'],
            params={'updateMask': 'displayName,conditions,documentation'}, json=body)
        verified = api(session, 'GET', base + after['name'])
        assert verified['conditions'][0]['conditionMatchedLog']['filter'] == application_error_filter(environment)
        assert verified['notificationChannels'] == before['notificationChannels']
        assert verified.get('alertStrategy') == before.get('alertStrategy')
    return {'environment': environment, 'policy': before['name'], 'updated': apply,
            'filter': application_error_filter(environment),
            'existingNotificationChannels': len(before['notificationChannels'])}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--environment', choices=['production', 'staging'], required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--create-missing', action='store_true', help='Allow one missing staging policy; never a duplicate or missing production policy')
    args = parser.parse_args()
    print(json.dumps(run(args.environment, apply=args.apply, create_missing=args.create_missing), indent=2))
