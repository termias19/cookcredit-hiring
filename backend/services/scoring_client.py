"""Client for the GPU scoring service (the authoritative, video-derived scorer).

The cook's clip is re-derived from PIXELS by the L4 Cloud Run service
(`serving/score_service` in the cookcredit-engine repo): MediaPipe motion +
SAM-segmented dice product-half -> a graded JSON. That is the tamper-resistant
half of the dual-score path; the on-device / trajectory score is only a claim.

Config (all via env; nothing hard-coded):
  SCORING_URL          base URL of the service, e.g. https://cookcredit-scoring-...-uc.a.run.app
  SCORING_AUDIENCE     OIDC audience for the ID token (defaults to SCORING_URL)
  SCORING_AUTH         "gcp" (default) -> mint a Google ID token from the runtime SA;
                       "none" -> no Authorization header (only for a local/unauthenticated endpoint)
  SCORING_TIMEOUT_SEC  per-request timeout (default 180; one score takes up to ~72s + cold start)
  SCORING_MAX_RETRIES  attempts for cold-start/5xx/401 (default 3)

The service scales to zero, so the FIRST request after idle pays a cold start and
may briefly 503 — we retry with exponential backoff. A 401/403 triggers one token
refresh + retry (a stale cached token). Raises ScoringError on definitive failure.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Optional

import requests

log = logging.getLogger(__name__)


class ScoringError(RuntimeError):
    """The scoring service could not produce a result (network / auth / 5xx / bad body)."""


class ScoringNotConfigured(ScoringError):
    """SCORING_URL is unset — the recompute path has nothing to call."""


def is_configured() -> bool:
    return bool(os.environ.get("SCORING_URL", "").strip())


def _base_url() -> str:
    url = os.environ.get("SCORING_URL", "").strip().rstrip("/")
    if not url:
        raise ScoringNotConfigured("SCORING_URL is not set")
    return url


def _fetch_id_token(audience: str) -> str:
    """Mint a Google-signed OIDC ID token for `audience` from the ambient identity
    (the Cloud Run runtime service account in prod, or ADC locally). No keys here —
    inside GCP the metadata server signs it. Raises ScoringError if unavailable."""
    try:
        import google.auth.transport.requests as greq
        import google.oauth2.id_token as gidtoken
    except Exception as exc:  # google-auth not installed
        raise ScoringError(f"google-auth unavailable for SCORING_AUTH=gcp: {exc}") from exc
    try:
        return gidtoken.fetch_id_token(greq.Request(), audience)
    except Exception as exc:
        raise ScoringError(f"could not mint ID token for {audience}: {exc}") from exc


def _auth_header(force_refresh: bool = False) -> dict:
    mode = os.environ.get("SCORING_AUTH", "gcp").strip().lower()
    if mode == "none":
        return {}
    audience = os.environ.get("SCORING_AUDIENCE", "").strip() or _base_url()
    token = _fetch_id_token(audience)
    return {"Authorization": f"Bearer {token}"}


def health() -> dict:
    """GET /health (NOT /healthz — the GFE swallows that). Returns the JSON body
    ({ok, gpu, device}) or raises ScoringError."""
    url = f"{_base_url()}/health"
    headers = _auth_header()
    try:
        r = requests.get(url, headers=headers, timeout=30)
    except requests.RequestException as exc:
        raise ScoringError(f"health request failed: {exc}") from exc
    if not r.ok:
        raise ScoringError(f"health {r.status_code}: {r.text[:200]}")
    return r.json()


def score_video(video_bytes: bytes, profile_id: str,
                content_type: str = "video/webm", knife_hand: str = "auto") -> dict:
    """POST the clip to /score and return the graded JSON (motion_half, product_half,
    verdict, ...). Handles cold start (retry on 5xx/timeout) and a stale token (one
    refresh on 401/403). Raises ScoringError after exhausting retries."""
    url = f"{_base_url()}/score"
    timeout = float(os.environ.get("SCORING_TIMEOUT_SEC", "180"))
    max_retries = max(1, int(os.environ.get("SCORING_MAX_RETRIES", "3")))

    refreshed = False
    last_err: Optional[str] = None
    for attempt in range(max_retries):
        try:
            headers = _auth_header(force_refresh=refreshed)
            files = {"video": ("clip", video_bytes, content_type)}
            data = {"profile_id": profile_id, "knife_hand": knife_hand}
            r = requests.post(url, headers=headers, files=files, data=data, timeout=timeout)
        except requests.RequestException as exc:
            last_err = f"network: {exc}"
            _backoff(attempt)
            continue

        if r.status_code in (401, 403) and not refreshed:
            # Stale/wrong-audience token -> refresh once and retry immediately.
            refreshed = True
            last_err = f"auth {r.status_code}: {r.text[:160]}"
            continue
        if r.status_code >= 500 or r.status_code == 429:
            # Cold start / transient -> backoff + retry.
            last_err = f"{r.status_code}: {r.text[:160]}"
            _backoff(attempt)
            continue
        if not r.ok:
            raise ScoringError(f"score {r.status_code}: {r.text[:300]}")
        try:
            return r.json()
        except ValueError as exc:
            raise ScoringError(f"score returned non-JSON: {exc}") from exc

    raise ScoringError(f"scoring failed after {max_retries} attempts: {last_err}")


def _backoff(attempt: int) -> None:
    # 1s, 2s, 4s, ... capped — short enough to stay within a Cloud Tasks dispatch.
    time.sleep(min(2 ** attempt, 8))


def fetch_video_bytes(video_url: str, max_bytes: int = 80 * 1024 * 1024,
                      *, owner_uid=None, generation=None) -> tuple[bytes, str]:
    """Read an owner- and generation-bound object through Storage, never a URL fetch."""
    from services.assessment_media import read_recording
    try:
        return read_recording(video_url, owner_uid, generation, max_bytes)
    except Exception as exc:
        raise ScoringError('Recording could not be read from authorized storage') from exc
