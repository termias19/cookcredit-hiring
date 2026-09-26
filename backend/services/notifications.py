"""Push notifications (Firebase Cloud Messaging).

Best-effort, fire-and-forget: a failure here must NEVER break the request that triggered it
(mirrors the SendGrid email pattern in routes/cook_application.py). The server-side SEND path
lives here, deliberately separate from services/firebase.py (which stays Auth + Storage only).
Reads users.fcm_token (captured today via PATCH /api/auth/me).

Reliable on Android (the common phone in Addis). Web push on iOS needs the PWA installed to the
home screen (iOS 16.4+); the durable in-app inbox is the fallback when a push can't be delivered.
"""
import logging

log = logging.getLogger(__name__)


def fcm_tokens_for(session, user_ids):
    """Return the non-null FCM tokens for the given user ids (de-duplicated input).
    Call this INSIDE the db_session block, then send AFTER commit so a pooled
    connection isn't held during the FCM network call."""
    ids = [u for u in dict.fromkeys(user_ids) if u]
    if not ids:
        return []
    from models import User
    rows = (session.query(User.fcm_token)
            .filter(User.id.in_(ids), User.fcm_token.isnot(None))
            .all())
    return [r[0] for r in rows if r[0]]


def send_push(tokens, title, body, data=None):
    """Multicast a notification to the given FCM tokens. No-op on an empty list; any
    error is logged and swallowed (never raised) so the caller's request still succeeds."""
    tokens = [t for t in tokens if t]
    if not tokens:
        return
    try:
        # Touch the firebase-admin app so the default app is initialized (get_auth is
        # already exercised by the auth middleware). messaging uses that default app.
        from services.firebase import get_auth
        get_auth()
        from firebase_admin import messaging
        msg = messaging.MulticastMessage(
            tokens=tokens,
            notification=messaging.Notification(title=title, body=body),
            data={k: str(v) for k, v in (data or {}).items()},
        )
        messaging.send_each_for_multicast(msg)
    except Exception:
        log.exception("FCM push send failed (title=%s, n=%d)", title, len(tokens))


def notify_beam_created(tokens, beam):
    """Alert matched cooks that a new beam landed in their city."""
    snippet = (beam.craving_text or "").strip()[:120]
    send_push(
        tokens,
        title="New craving nearby",
        body=snippet or f"An eater in {beam.city or 'your area'} is craving a meal.",
        data={"type": "beam", "beamId": str(beam.id), "scope": beam.scope or "citywide"},
    )


def notify_beam_chosen(tokens, beam):
    """Tell the chosen cook the eater picked them."""
    send_push(
        tokens,
        title="You were picked",
        body="An eater chose you for their craving. Open CookCredit to connect.",
        data={"type": "beam_chosen", "beamId": str(beam.id)},
    )
