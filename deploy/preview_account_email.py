"""Render the existing account mail template with a nonfunctional review link.

This does not send email, change Firebase templates or configure inbox branding.
"""
import os
from pathlib import Path
import shutil
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'backend'))
from services.account_email import account_email_content

destination = root.parent / 'work' / 'email-branding-review'
destination.mkdir(parents=True, exist_ok=True)
shutil.copyfile(root / 'frontend/public/cookcredit-mark-orange.png',
                destination / 'cookcredit-mark-orange.png')
os.environ['FRONTEND_URL'] = 'https://cookcredit-hiring-staging.web.app'
for kind in ('verify', 'reset', 'welcome'):
    _, _, markup = account_email_content(kind, 'https://example.invalid/review-only')
    markup = markup.replace('https://cookcredit.com/cookcredit-mark-orange.png',
                            './cookcredit-mark-orange.png')
    markup = markup.replace(
        '<table role="presentation" width="100%"',
        '<p style="margin:0;padding:12px 16px;font:13px Arial,sans-serif;background:#fff7ed">'
        'Template preview only. Not sent or enabled. '
        '<a href="verify.html">Verification</a> · <a href="reset.html">Password reset</a> · '
        '<a href="welcome.html">Welcome</a></p><table role="presentation" width="100%"', 1)
    (destination / f'{kind}.html').write_text(markup, encoding='utf-8')
print(destination)
