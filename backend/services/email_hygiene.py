"""Lightweight email hygiene for signup abuse control — no external deps, no network calls.

The strongest anti-bot control is requiring a VERIFIED email before any privilege
(middleware.auth.require_verified_email). This module adds a cheap pre-filter that rejects
KNOWN disposable/throwaway domains at account creation so we don't even mint a DB row for them.

The blocklist is intentionally CONSERVATIVE (well-known temp-mail providers only) to avoid
false-positives on real users — never put a major mailbox provider here. Expand from the community
`disposable-email-domains` list if abuse warrants it.
"""

# Well-known disposable / temporary-inbox providers. Conservative on purpose.
_DISPOSABLE = frozenset({
    "mailinator.com", "guerrillamail.com", "guerrillamail.info", "guerrillamailblock.com",
    "sharklasers.com", "grr.la", "spam4.me", "10minutemail.com", "10minutemail.net",
    "10minutemail.co.uk", "tempmail.com", "temp-mail.org", "temp-mail.io", "tempmail.net",
    "yopmail.com", "yopmail.net", "throwawaymail.com", "getnada.com", "nada.email",
    "dispostable.com", "trashmail.com", "trashmail.net", "maildrop.cc", "mailnesia.com",
    "mohmal.com", "fakeinbox.com", "tempinbox.com", "emailondeck.com", "spamgourmet.com",
    "mailcatch.com", "tempr.email", "discard.email", "mailsac.com", "moakt.com",
    "tmpmail.org", "tmpmail.net", "mintemail.com", "mytemp.email", "burnermail.io",
    "33mail.com", "fakemail.net", "tempmailo.com", "1secmail.com", "inboxkitten.com",
})


def email_domain(email):
    """Lowercased domain part of an email, or '' if malformed."""
    if not isinstance(email, str) or "@" not in email:
        return ""
    return email.rsplit("@", 1)[1].strip().lower().rstrip(".")


def is_disposable_email(email):
    """True if the email's domain is a known disposable/temp-mail provider."""
    return email_domain(email) in _DISPOSABLE


def normalize_email(email):
    """Canonical key for de-duplication / abuse-logging (NOT for auth): lowercase, drop a Gmail
    +tag and dots in the local part (Gmail ignores both, so a.b+x@gmail == ab@gmail). Only the big
    providers that document this behavior are normalized; everyone else keeps their local part."""
    if not isinstance(email, str) or "@" not in email:
        return (email or "").strip().lower()
    local, domain = email.rsplit("@", 1)
    local = local.strip().lower().split("+", 1)[0]
    domain = domain.strip().lower().rstrip(".")
    if domain in ("gmail.com", "googlemail.com"):
        local = local.replace(".", "")
        domain = "gmail.com"
    return f"{local}@{domain}"
