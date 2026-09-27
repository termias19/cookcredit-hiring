"""Shared authenticated Google Workspace mail transport."""
import os, smtplib, ssl
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

def send_google_smtp(recipient, subject, plain, markup, *, headers=None):
    """Authenticated Google submission; never log credentials or action links."""
    sender = os.environ['GOOGLE_SMTP_USER'].strip()
    password = ''.join(os.environ['GOOGLE_SMTP_APP_PASSWORD'].split())
    message = EmailMessage()
    # Use the authenticated mailbox. An unverified From alias may be rewritten
    # by Google and must not be silently presented as an installed sender.
    message['From'] = formataddr(('CookCredit', sender))
    message['To'] = recipient
    message['Reply-To'] = 'CookCredit <connectwithus@cookcredit.com>'
    message['Subject'] = subject
    message['Date'] = formatdate(localtime=False)
    message['Message-ID'] = make_msgid(domain='cookcredit.com')
    message['Auto-Submitted'] = 'auto-generated'
    for key, value in (headers or {}).items():
        if key in ('List-Unsubscribe', 'List-Unsubscribe-Post'):
            message[key] = value
    message.set_content(plain)
    message.add_alternative(markup, subtype='html')
    try:
        with smtplib.SMTP('smtp.gmail.com', 587, timeout=15) as smtp:
            smtp.ehlo()
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
            smtp.login(sender, password)
            refused = smtp.send_message(message, from_addr=sender, to_addrs=[recipient])
            if refused:
                raise RuntimeError('email_provider_unavailable')
    except (OSError, smtplib.SMTPException):
        raise RuntimeError('email_provider_unavailable') from None
