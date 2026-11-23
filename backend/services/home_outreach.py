"""Owner outreach drafts. This module never queues or sends a message.

Reuse the existing campaign schema and Home audit/idempotency controls. Manual
sharing has no recipient imports, health targeting, tracking or paid SMS.
"""
import html
import re
from datetime import datetime, timezone
from sqlalchemy import select
from models.home_outreach import HomeCampaign
from services import home_visits as visits
from services import home_customers as customers

IMAGES = {'dinner': ('home-dinner.jpg', 'Illustrative roast chicken and vegetables'),
          'stew': ('home-stew.jpg', 'Illustrative vegetable and white bean stew')}
DESTINATIONS = {'enroll': ('Choose my service needs', 'enroll'),
                'help': ('Ask us to call', 'help'), 'visits': ('Open my visits', 'visits')}


def fields(body):
    values = {}
    for key, field, cap in (('subject', 'subject', 150), ('body', 'body', 3000), ('postalAddress', 'postal_address', 500)):
        value = body.get(key, '')
        if not isinstance(value, str) or len(value.strip()) > cap or re.search(r'[\x00-\x08\x0b-\x1f\x7f]', value):
            visits.fail('invalid_campaign', 'Check the subject, message and mailing address.')
        values[field] = value.strip()
    if not values['subject'] or not values['body'] or '\n' in values['subject'] or '\r' in values['subject']:
        visits.fail('invalid_campaign', 'Enter a subject on one line and a message.')
    design = body.get('design', {})
    visits.strict_object(design, (), ('image', 'destination'))
    image, destination = design.get('image', 'dinner'), design.get('destination', 'enroll')
    if not isinstance(image, str) or image not in IMAGES or not isinstance(destination, str) or destination not in DESTINATIONS:
        visits.fail('invalid_campaign', 'Choose a food picture and a CookCredit destination.')
    return {**values, 'design': {'image': image, 'destination': destination}}


def save(session, actor, body, campaign_id=None):
    visits.strict_object(body, ('action',), ('subject', 'body', 'postalAddress', 'design', 'revision'))
    action = body['action']
    if action not in ('save', 'trash', 'restore'):
        visits.fail('invalid_campaign', 'Choose save, trash or restore. Sending is not enabled here.')
    row = session.execute(select(HomeCampaign).where(HomeCampaign.id == campaign_id).with_for_update()).scalar_one_or_none() if campaign_id else HomeCampaign()
    if row is None:
        visits.fail('not_found', 'This draft was not found.', 404)
    if campaign_id and (type(body.get('revision')) is not int or body['revision'] != row.revision):
        visits.fail('stale_version', 'This draft changed. Refresh before saving.', 409)
    if not campaign_id and action != 'save':
        visits.fail('invalid_campaign', 'Save a draft first.')
    if action == 'save':
        if row.status == 'trashed':
            visits.fail('stale_version', 'Restore this draft first.', 409)
        for key, value in fields(body).items():
            setattr(row, key, value)
    row.status = 'trashed' if action == 'trash' else 'draft'
    row.next_run_at, row.run_at, row.cursor, row.interval_days = None, None, None, 0
    row.revision = (row.revision or 0) + 1
    row.updated_at = datetime.now(timezone.utc)
    session.add(row)
    session.flush()
    customers.audit(session, actor, 'outreach_' + action, row.id)
    # No private copy or mailing address in immutable command history.
    return {'id': str(row.id), 'revision': row.revision}


def render_email(body, base):
    """Export a reviewable email, with fixed URLs and escaped plain-text input.

    The owner shares this manually using the existing verified Send-as alias.
    Opt-out replies go to customer service; no fake token/subscription is used.
    """
    value = fields(body)
    if not value['postal_address']:
        visits.fail('invalid_campaign', 'Add a valid business mailing address before preparing advertising email. It appears only in the email footer.')
    picture, alt = IMAGES[value['design']['image']]
    button, target = DESTINATIONS[value['design']['destination']]
    link = base.rstrip('/') + '/#' + target
    support = 'connectwithus@cookcredit.com'
    optout = 'mailto:' + support + '?subject=Unsubscribe%20from%20Home%20offers'
    footer = 'Advertisement from CookCredit Home. To stop marketing emails, reply “unsubscribe” or email ' + support + '. Account, visit and payment messages continue.'
    plain = f'{value["subject"]}\n\n{value["body"]}\n\n{button}: {link}\n\nEnrollment is free. Review your full quote before paying for a visit.\n\n{footer}\n{value["postal_address"]}'
    escape = lambda text: html.escape(text, quote=True).replace('\n', '<br>')
    markup = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;background:#f7f5ef;color:#222722;font-family:Arial,sans-serif;font-size:18px;line-height:1.6">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td style="padding:24px 12px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;margin:auto;background:#fffdf8;border:1px solid #d4d6cd">
<tr><td style="padding:24px 28px;font-family:Georgia,serif;font-size:28px">CookCredit <span style="font-family:Arial,sans-serif;font-size:16px">At home</span></td></tr>
<tr><td><img src="{escape(base)}/assets/{picture}" width="600" alt="{alt}" style="display:block;width:100%;max-width:600px;height:auto;border:0"></td></tr>
<tr><td style="padding:28px"><h1 style="font-family:Georgia,serif;font-size:32px;font-weight:normal;line-height:1.2;margin:0 0 20px">{escape(value['subject'])}</h1>
<p style="margin:0 0 24px">{escape(value['body'])}</p>
<p><a href="{escape(link)}" style="display:inline-block;padding:16px 24px;background:#294f3f;color:#fff;text-decoration:none;font-size:18px;font-weight:bold;border-radius:4px">{button}</a></p>
<p style="font-size:16px">Enrollment is free. Review your full quote before paying for a visit.</p>
<p style="font-size:16px">Prefer a conversation? <a href="{escape(base)}/#help" style="color:#294f3f">Ask us to call you</a>.</p>
<p style="font-size:14px;color:#515a50">Illustrative meal. Meals and ingredients are agreed for each visit.</p>
<hr style="border:0;border-top:1px solid #d4d6cd;margin:28px 0">
<p style="font-size:16px">{escape(footer)}</p><p style="font-size:16px">{escape(value['postal_address'])}</p>
<p style="font-size:16px"><a href="{optout}" style="color:#294f3f">Unsubscribe from Home offers</a></p>
<p style="font-size:16px">Customer service: <a href="mailto:{support}" style="color:#294f3f">{support}</a></p>
<p style="font-size:14px"><a href="https://cookcredit.com/privacy.html" style="color:#515a50">Privacy</a> · <a href="https://cookcredit.com/terms.html" style="color:#515a50">Terms</a></p>
</td></tr></table></td></tr></table></body></html>'''
    return {'subject': value['subject'], 'plain': plain, 'html': markup}
