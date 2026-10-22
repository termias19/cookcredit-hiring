"""Inspect or update the existing Hiring log alert; never create a parallel policy."""
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


def run(environment, apply=False):
    session = client()
    base = 'https://monitoring.googleapis.com/v3/'
    data = api(session, 'GET', base + 'projects/' + PROJECT + '/alertPolicies')
    if data.get('nextPageToken'):
        raise RuntimeError('Policy listing truncated; inspect before updating')
    names = {'CookCredit hiring ' + environment + ' stalled or failed delivery',
             'CookCredit hiring ' + environment + ' application and delivery failures'}
    found = [row for row in data.get('alertPolicies', []) if row.get('displayName') in names]
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
    args = parser.parse_args()
    print(json.dumps(run(args.environment, apply=args.apply), indent=2))
