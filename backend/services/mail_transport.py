"""Shared authenticated Google Workspace mail transport."""
import os, smtplib, ssl
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid


def google_smtp_sender():
    login = os.environ['GOOGLE_SMTP_USER'].strip()
    public = os.getenv('GOOGLE_SMTP_VERIFIED_FROM', '').strip() or login
    # This is an operator attestation of an existing Google Send-as grant,
    # never a caller-supplied header or a substitute for provider verification.
    if (any(c.isspace() for c in login + public)
            or (public != login and public != 'connectwithus@cookcredit.com')):
        raise RuntimeError('email_sender_not_approved')
    return login, public


def send_google_smtp(recipient, subject, plain, markup, *, headers=None):
    """Authenticated Google submission; never log credentials or action links."""
    login, sender = google_smtp_sender()
    password = ''.join(os.environ['GOOGLE_SMTP_APP_PASSWORD'].split())
    message = EmailMessage()
    # Default to the login mailbox; Home may explicitly use the existing,
    # verified customer-service alias without changing SMTP credentials.
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
            smtp.login(login, password)
            refused = smtp.send_message(message, from_addr=sender, to_addrs=[recipient])
            if refused:
                raise RuntimeError('email_provider_unavailable')
    except (OSError, smtplib.SMTPException):
        raise RuntimeError('email_provider_unavailable') from None
