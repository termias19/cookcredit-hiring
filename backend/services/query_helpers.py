"""Reusable query guards: row-ownership enforcement + pagination.

ROW-LEVEL SECURITY MODEL
------------------------
This app does NOT use Postgres RLS, and that is intentional: Postgres RLS is for
architectures where untrusted clients talk to the database directly (Supabase /
PostgREST style). Here the trusted Flask backend is the only DB client (single
role), so authorization is enforced in the APPLICATION layer — every query is
scoped to the authenticated user (g.user_id).

Today every endpoint is self-scoped (no endpoint takes a client-supplied row id),
so there is no cross-user access. As soon as an endpoint fetches a row by an id
from the request (bookings, reviews, messages), it MUST call owned_or_404() so a
user can only read/mutate rows they own. Use these helpers to keep that uniform.
"""
from flask import request, abort

DEFAULT_PER_PAGE = 20
MAX_PER_PAGE = 100


def owned_or_404(obj, owner_fields, uid):
    """Return `obj` only if `uid` owns it; otherwise abort 404.

    404 (not 403) on purpose — a 403 would confirm the row exists to someone who
    shouldn't see it. `owner_fields` is an attribute name or list of names (e.g.
    a booking is owned by either its eater_id or cook_id).
    """
    if obj is None:
        abort(404)
    fields = [owner_fields] if isinstance(owner_fields, str) else list(owner_fields)
    if not any(getattr(obj, f, None) == uid for f in fields):
        abort(404)
    return obj


def paginate(query, serialize=lambda row: row.to_dict()):
    """Apply cursorless page/perPage pagination to a SQLAlchemy query.

    Reads ?page= and ?perPage= (clamped to MAX_PER_PAGE). Fetches one extra row
    to compute hasMore without a second COUNT query. Returns a JSON-ready dict.
    """
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    try:
        per_page = int(request.args.get("perPage", DEFAULT_PER_PAGE))
    except (TypeError, ValueError):
        per_page = DEFAULT_PER_PAGE
    per_page = max(1, min(per_page, MAX_PER_PAGE))

    rows = query.limit(per_page + 1).offset((page - 1) * per_page).all()
    has_more = len(rows) > per_page
    items = rows[:per_page]
    return {
        "items": [serialize(r) for r in items],
        "page": page,
        "perPage": per_page,
        "hasMore": has_more,
    }
