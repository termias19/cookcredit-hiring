"""Read-only release check. No messages, credential files, or config writes.

python scripts/check_firebase_email_branding.py --project foodnlit-1123e \
    --account eassefa@cookcredit.com
An exit code of zero checks cloud configuration, NOT actual inbox delivery.
"""
import argparse
import json
import os
import subprocess
import sys
import requests


def branding_checks(mail):
    """Accepted policy: CookCredit domain with Google's native branded templates.

    An unset display name and %APP_NAME% subject use the Firebase public app
    name. That substitution must still be checked in a received email. The
    owner accepts CookCredit; an exact CookCredit Team override is not required.
    """
    dns = mail.get('dnsInfo', {})
    checks = {
        'googleManagedDelivery': mail.get('method') == 'DEFAULT',
        'cookcreditSenderDomainApplied': dns.get('customDomain') == 'cookcredit.com' and dns.get('useCustomDomain') is True,
        'cookcreditActionLink': mail.get('callbackUri') == 'https://cookcredit.com/__/auth/action',
    }
    for kind in ('verifyEmailTemplate', 'resetPasswordTemplate'):
        template = mail.get(kind, {})
        subject = template.get('subject', '')
        checks[kind] = (
            template.get('senderDisplayName', '') in ('', 'CookCredit', 'CookCredit Team')
            and template.get('senderLocalPart') == 'noreply'
            and ('CookCredit' in subject or '%APP_NAME%' in subject)
        )
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True)
    parser.add_argument('--account', required=True)
    args = parser.parse_args()
    token = subprocess.run(['gcloud.cmd' if os.name == 'nt' else 'gcloud', 'auth',
        'print-access-token', '--account='+args.account, '--project='+args.project],
        capture_output=True, text=True, check=True).stdout.strip()
    response = requests.get(
        f'https://identitytoolkit.googleapis.com/admin/v2/projects/{args.project}/config',
        headers={'Authorization': 'Bearer '+token, 'x-goog-user-project': args.project}, timeout=20)
    if not response.ok:
        print(json.dumps({'configurationReady': False, 'httpStatus': response.status_code}))
        return 2
    mail = response.json().get('notification', {}).get('sendEmail', {})
    checks = branding_checks(mail)
    ready = all(checks.values())
    print(json.dumps({'project': args.project, 'configurationReady': ready, 'checks': checks,
        'acceptedBrand': 'CookCredit', 'resolvedInboxBrandVerified': False,
        'inboxDeliveryVerified': False}, indent=2))
    return 0 if ready else 2


if __name__ == '__main__':
    sys.exit(main())
