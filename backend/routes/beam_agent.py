"""Beam concierge — the AI agent behind the beam composer.

An eater chats about what they're craving; the agent asks at most a question or
two, then produces a structured BEAM DRAFT (craving text written for cooks, the
city, and the scope). The client shows the draft in the normal composer for the
HUMAN to confirm — the agent never broadcasts anything itself, and the existing
POST /api/beams (auth + validation + matching) is untouched.

Wire shape:
  POST /api/beams/agent   body: {messages: [{role, content}...], city?, lang?}
                          -> 200 {reply, draft: null | {craving_text, city, scope}}
                          -> 503 {error} when no GEMINI_API_KEY is configured

Every turn is one Gemini API call with a strict JSON schema (structured
outputs), so the response always parses. Chat history lives on the client and
is re-sent each turn (the API is stateless); we cap and sanitize it here.
"""
import json
import logging
import os

from flask import Blueprint, jsonify, g, request

from extensions import limiter
from middleware.auth import require_auth

beam_agent_bp = Blueprint("beam_agent", __name__)
log = logging.getLogger(__name__)

MODEL = os.environ.get("BEAM_AGENT_MODEL", "gemini-2.5-flash")
MAX_TURNS = 24          # messages per request (the whole visible chat)
MAX_MSG_CHARS = 2000    # per message
MAX_TOKENS = 1024       # concierge replies are deliberately short

SYSTEM_PROMPT = """You are the beam concierge for CookCredit, a marketplace where people
broadcast a food craving (a "beam") to skill-verified home cooks in their city, and cooks
respond with an offer and a price.

Your job: help the eater turn a vague craving into a great beam, fast.

- Reply in the language the user writes in (English, Amharic, Tigrinya, Afaan Oromoo, or
  Spanish). Keep replies to one to three short sentences. Ask at most ONE question per turn,
  and only when the answer would genuinely improve the beam (servings, timing, spice level,
  budget). Never interrogate; never repeat a question.
- As soon as you know WHAT they crave and WHICH CITY they're in, emit the draft. Do not keep
  chatting once a good draft is possible. If the city was provided in the context line, use
  it without asking.
- craving_text is what the cooks read: write it in the user's language, first person plural
  is fine, include dish, servings, timing, and budget hints when known. Under 400 characters.
  Do not invent details the user never gave (no fabricated budgets, allergies, or times).
- scope is "nearby" only when the user says they want somewhere close by; otherwise
  "citywide".
- You never place orders, never quote prices (cooks set prices in their responses), and never
  give medical or allergy guarantees — if allergies come up, put the allergy note into
  craving_text so cooks see it.
- If the user asks about anything other than composing a beam, answer in one sentence and
  steer back to the craving.

Every response must follow the JSON schema you are given: `reply` is the chat message shown
to the user; `draft` is null until the beam is ready, then the completed draft object. When
you emit a draft, `reply` should briefly say the beam is ready to review and send."""

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "reply": {"type": "string"},
        "draft": {
            "anyOf": [
                {"type": "null"},
                {
                    "type": "object",
                    "properties": {
                        "craving_text": {"type": "string"},
                        "city": {"type": "string"},
                        "scope": {"type": "string", "enum": ["nearby", "citywide"]},
                    },
                    "required": ["craving_text", "city", "scope"],
                    "additionalProperties": False,
                },
            ]
        },
    },
    "required": ["reply", "draft"],
    "additionalProperties": False,
}


# ── pure helpers (unit-tested without the API) ───────────────────────────────────
def sanitize_messages(raw):
    """Validate + normalize the client-sent chat history for the model.

    Returns a list of {role, content} dicts (roles only 'user'/'assistant',
    content non-empty strings, capped in count and length, first message forced
    to 'user'), or None if the payload is unusable."""
    if not isinstance(raw, list) or not raw:
        return None
    out = []
    for m in raw[-MAX_TURNS:]:
        if not isinstance(m, dict):
            return None
        role = m.get("role")
        content = m.get("content")
        if role not in ("user", "assistant") or not isinstance(content, str):
            return None
        content = content.strip()[:MAX_MSG_CHARS]
        if not content:
            continue
        # The API combines consecutive same-role messages; keep them as-is.
        out.append({"role": role, "content": content})
    while out and out[0]["role"] != "user":
        out.pop(0)
    if not out or out[-1]["role"] != "user":
        return None
    return out


def validate_draft(d):
    """The model's draft, re-checked server-side before it reaches the client.
    Returns a clean draft dict or None. (The draft only PREFILLS the composer —
    POST /api/beams still does its own authoritative validation on send.)"""
    if not isinstance(d, dict):
        return None
    craving = (d.get("craving_text") or "").strip()[:500]
    city = (d.get("city") or "").strip()[:120]
    scope = d.get("scope")
    if not craving or not city or scope not in ("nearby", "citywide"):
        return None
    return {"craving_text": craving, "city": city, "scope": scope}


def context_line(city, lang):
    """One compact context line appended to the system prompt (kept OUT of the
    user-visible chat so the model treats it as operator context, not user text)."""
    parts = []
    if city:
        parts.append(f"The user's saved city is: {city}.")
    if lang:
        parts.append(f"The app's active language code is: {lang}.")
    return " ".join(parts)


def conversation_text(messages):
    """Render the bounded history as data for Gemini, not as model instructions."""
    return "Conversation to continue:\n\n" + "\n\n".join(
        f"{item['role'].upper()}:\n{item['content']}" for item in messages
    )


# ── the endpoint ─────────────────────────────────────────────────────────────────
@beam_agent_bp.route("", methods=["POST"])
@beam_agent_bp.route("/", methods=["POST"])
@require_auth
@limiter.limit("30 per hour", key_func=lambda: g.user_id)
def beam_agent_chat():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return jsonify({"error": "assistant unavailable"}), 503

    data = request.get_json(silent=True) or {}
    messages = sanitize_messages(data.get("messages"))
    if messages is None:
        return jsonify({"error": "messages must be a non-empty list ending with a user turn"}), 400
    city = (data.get("city") or "").strip()[:120]
    lang = (data.get("lang") or "").strip()[:8]

    system = SYSTEM_PROMPT
    ctx = context_line(city, lang)
    if ctx:
        system = f"{system}\n\n{ctx}"

    # Deferred so an unused concierge does not add SDK startup work to every API process.
    from google import genai
    from google.genai import errors

    client = genai.Client(api_key=api_key)
    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=conversation_text(messages),
            config={
                "system_instruction": system,
                "max_output_tokens": MAX_TOKENS,
                "temperature": 0.2,
                "response_mime_type": "application/json",
                "response_json_schema": OUTPUT_SCHEMA,
            },
        )
    except errors.APIError as exc:
        code = int(getattr(exc, "code", 0) or 0)
        log.warning("beam agent Gemini API error %s: %s", code, getattr(exc, "message", ""))
        if code == 429:
            return jsonify({"error": "assistant is busy — try again in a moment"}), 429
        return jsonify({"error": "assistant unavailable"}), 502
    except (OSError, TimeoutError):
        return jsonify({"error": "assistant unreachable"}), 502
    finally:
        client.close()

    text = response.text or ""
    try:
        parsed = json.loads(text)
    except (ValueError, TypeError):
        log.warning("beam agent returned unparseable Gemini output")
        return jsonify({"error": "assistant unavailable"}), 502

    return jsonify({
        "reply": (parsed.get("reply") or "").strip()[:2000],
        "draft": validate_draft(parsed.get("draft")),
    }), 200
