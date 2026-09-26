"""Dual skill-scoring path — the attempt state machine, reconciliation, and recompute.

Flow:
  1. /api/skills/submit records an ON-DEVICE (provisional, client-claimed) score and a
     cheap server recompute of the trajectory, creates a PROVISIONAL SkillAttempt, and
     enqueues a recompute. Idempotent on (user_id, session_id).
  2. The recompute pulls the uploaded VIDEO and calls the GPU scorer (pixels -> motion +
     SAM dice). `reconcile()` compares the video truth to the client's claim:
        - MOTION is the anti-tamper check (does the video's technique match the claim?)
        - PRODUCT (dice) is the skill verdict (where cut skill actually lives)
     and advances the attempt to VERIFIED | DISPUTED | INSUFFICIENT.
  3. A credential is stamped on the CookProfile ONLY on VERIFIED.

Why not a single numeric delta between the two scores? They measure different axes — the
on-device score is rhythm/motion, the GPU's authoritative score is dice product quality —
so a raw subtraction is meaningless. The COMPARABLE agreement signal is the technique
(motion) match; that is what flags tampering.
"""
from __future__ import annotations

import logging
import os
import threading
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy.exc import IntegrityError
from typing import Callable, Optional

from services.database import db_session
from services import scoring_client
from services.scoring_client import ScoringError
from services.skill_scoring import PASS_SCORE, TIERS
from services.hiring_applications import sync_application_for_attempt
from models import (
    SkillAttempt, SkillAttemptEvent, CookProfile,
    is_valid_transition, ATTEMPT_TERMINAL,
)

log = logging.getLogger(__name__)

MAX_RECOMPUTES = int(os.environ.get("SCORING_MAX_RECOMPUTES", "5"))


class RecomputeBusy(RuntimeError):
    """Another worker has an unexpired lease; the delivery should retry later."""


def _utcnow():
    return datetime.now(timezone.utc)


def _tier(score: Optional[float]) -> Optional[str]:
    """Tier for a VERIFIED score (provisional thresholds, shared with the oscillation
    scorer; recalibrate on the pilot corpus)."""
    if score is None:
        return None
    for thr, name in TIERS:
        if score >= thr:
            return name
    return None


def _sync_hiring_if_linked(session, attempt: SkillAttempt) -> None:
    """Only engine handoff attempts can belong to a hiring application."""
    if (attempt.metadata_ or {}).get('source') == 'cookcredit-skill-live':
        sync_application_for_attempt(session, attempt.id)


# ── state-machine writes (append-only) ─────────────────────────────────────────

def transition(session, attempt: SkillAttempt, to_state: str, detail: Optional[dict] = None) -> None:
    """Advance an attempt forward and append the transition event. Raises ValueError
    on an illegal move so a bug can't silently corrupt the (append-only) history."""
    frm = attempt.verification_state
    if frm == to_state and to_state == "VERIFYING":
        pass  # idempotent recompute retry — allowed, still logged
    elif not is_valid_transition(frm, to_state):
        raise ValueError(f"illegal skill-attempt transition {frm} -> {to_state}")
    session.add(SkillAttemptEvent(attempt_id=attempt.id, from_state=frm,
                                  to_state=to_state, detail=detail))
    attempt.verification_state = to_state
    attempt.updated_at = _utcnow()
    if to_state in ATTEMPT_TERMINAL:
        attempt.dispatch_due_at = None
        attempt.dispatch_token = None
        attempt.recompute_lease_id = None
        attempt.recompute_lease_until = None


def create_or_get_attempt(session, *, user_id: str, session_id: str, profile_id: str,
                          on_device_score, on_device_block: dict, local_result: dict,
                          trajectory: list, metadata: dict, video_url: Optional[str]) -> tuple[SkillAttempt, bool]:
    """Idempotent create keyed by (user_id, session_id). A retried submit for the same
    client session returns the existing attempt (never re-scores / re-charges the GPU).
    Returns (attempt, created)."""
    existing = (session.query(SkillAttempt)
                .filter(SkillAttempt.user_id == user_id, SkillAttempt.session_id == session_id)
                .with_for_update()
                .one_or_none())
    if existing is not None:
        # Backfill a video that arrived on a retry (e.g. first submit had no clip yet).
        if video_url and not existing.video_url:
            existing.video_url = video_url
            existing.metadata_ = {**(existing.metadata_ or {}),
                                  **{k: metadata[k] for k in ('recording_path', 'recording_generation') if k in metadata}}
            existing.updated_at = _utcnow()
        if (existing.verification_state not in ATTEMPT_TERMINAL and existing.video_url
                and (existing.metadata_ or {}).get('recording_generation')
                and existing.dispatch_due_at is None):
            existing.dispatch_due_at = _utcnow()
        return existing, False

    local_score = local_result.get("skill_score") if local_result.get("ok") else None
    attempt = SkillAttempt(
        user_id=user_id, session_id=session_id, profile_id=profile_id,
        verification_state="PROVISIONAL",
        on_device_score=on_device_score, on_device_block=on_device_block or {},
        local_score=local_score, local_block=local_result,
        trajectory=trajectory, metadata_=metadata or {}, video_url=video_url,
        dispatch_due_at=_utcnow() if video_url and metadata.get('recording_generation') else None,
    )
    try:
        with session.begin_nested():
            session.add(attempt)
            session.flush()
    except IntegrityError:
        # Concurrent identical submits may both miss the initial lookup. The
        # database unique constraint is authoritative; do not abort the outer tx.
        existing = session.query(SkillAttempt).filter_by(user_id=user_id, session_id=session_id).one_or_none()
        if existing is None:
            raise
        return existing, False
    session.add(SkillAttemptEvent(attempt_id=attempt.id, from_state=None,
                                  to_state="PROVISIONAL", detail={"reason": "submitted"}))
    return attempt, True


# ── reconciliation (pure) ──────────────────────────────────────────────────────

def _scale_product(raw) -> Optional[float]:
    """Normalize the GPU product composite to 0..100. The engine reports it on 0..1
    (or already 0..100); clamp either way."""
    if raw is None:
        return None
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return None
    if v <= 1.0:
        v *= 100.0
    return round(max(0.0, min(100.0, v)), 2)


def reconcile(server_block: dict, *, local_result: dict, on_device_score) -> dict:
    """Decide the terminal state from the video truth vs the client claim.

    Returns {state, authoritative_score, tier, reconciliation}.
    """
    motion = server_block.get("motion_half") or {}
    product = server_block.get("product_half") or {}
    verdict = server_block.get("verdict") or {}

    gpu_technique = motion.get("technique")
    gpu_candidate = motion.get("candidate")
    gpu_low_calib = bool(motion.get("low_calibration"))
    product_ok = bool(product.get("ok"))
    technique_ok = bool(verdict.get("technique_ok"))
    authoritative = _scale_product(verdict.get("product_score"))

    local_tech = (local_result or {}).get("technique") or {}
    client_candidate = local_tech.get("candidate")
    client_low_calib = bool(local_tech.get("low_calibration"))

    motion_uncertain = gpu_technique in (None, "uncertain") or gpu_candidate is None
    technique_mismatch = bool(
        client_candidate and gpu_candidate
        and not gpu_low_calib and not client_low_calib
        and client_candidate != gpu_candidate
    )
    # Did the client CLAIM a real, passing chop? (only then is "no chop in the video" tamper)
    client_claimed_strong = bool(
        (local_result or {}).get("verified")
        or (on_device_score is not None and on_device_score >= PASS_SCORE)
    )

    recon = {
        "tamper_flag": False,
        "motion_match": (None if motion_uncertain else not technique_mismatch),
        "technique_claimed": client_candidate,
        "technique_video": gpu_candidate,
        "technique_ok_for_cut": technique_ok,
        "product_ok": product_ok,
        "is_dice": verdict.get("is_dice"),
        "product_score": authoritative,
        "on_device_score": float(on_device_score) if on_device_score is not None else None,
        # The two numbers measure different axes (motion rhythm vs dice product) — a raw
        # numeric delta is NOT meaningful. Technique (motion) match is the comparable signal.
        "comparable_numeric": False,
        "agreement": "unverifiable",
        "summary": verdict.get("summary"),
        "reason": None,
    }

    # 1) Tamper: the claim materially overstates what the video supports.
    if motion_uncertain and client_claimed_strong:
        recon.update(tamper_flag=True, agreement="mismatch",
                     reason="The uploaded video shows no detectable chopping, but a chopping "
                            "demonstration was submitted.")
        return {"state": "DISPUTED", "authoritative_score": None, "tier": None, "reconciliation": recon}
    if technique_mismatch:
        recon.update(tamper_flag=True, agreement="mismatch",
                     reason=f"The video shows a {gpu_candidate} motion but {client_candidate} was claimed.")
        return {"state": "DISPUTED", "authoritative_score": None, "tier": None, "reconciliation": recon}

    # 2) Insufficient: can't grade (not the user's claim, just an ungradeable capture).
    if motion_uncertain:
        recon.update(agreement="unverifiable",
                     reason="Couldn't detect a clear chopping bout in the video — retake with "
                            "your hands and the board in frame.")
        return {"state": "INSUFFICIENT", "authoritative_score": None, "tier": None, "reconciliation": recon}
    if not technique_ok:
        recon.update(agreement="match",  # motion was read, just the wrong cut
                     reason=verdict.get("summary") or "The technique didn't match the requested cut.")
        return {"state": "INSUFFICIENT", "authoritative_score": None, "tier": None, "reconciliation": recon}
    if not product_ok or authoritative is None:
        recon.update(agreement="match",
                     reason=product.get("reason") or "Couldn't grade the cut pieces — retake with the "
                            "finished pieces visible on the board.")
        return {"state": "INSUFFICIENT", "authoritative_score": None, "tier": None, "reconciliation": recon}

    # 3) Verified: video confirms the technique AND the pieces are gradeable.
    recon.update(agreement="match",
                 reason=verdict.get("summary") or f"Verified {gpu_candidate} — product quality {authoritative}.")
    return {"state": "VERIFIED", "authoritative_score": authoritative,
            "tier": _tier(authoritative), "reconciliation": recon}


# ── recompute orchestration ────────────────────────────────────────────────────

def run_recompute(attempt_id: str, *,
                  score_video: Callable[..., dict] = scoring_client.score_video,
                  fetch_video: Callable[..., tuple] = scoring_client.fetch_video_bytes) -> Optional[SkillAttempt]:
    """Pull the attempt's video, call the GPU scorer, reconcile, and advance state.
    Idempotent: a terminal attempt is returned untouched; transient failures leave it
    in VERIFYING (retryable) until INSUFFICIENT after MAX_RECOMPUTES. The GPU call (slow,
    network) runs OUTSIDE any DB transaction. score_video/fetch_video are injectable for tests."""
    # Short row lock grants a lease; no DB connection is held during inference.
    lease_id = uuid.uuid4()
    with db_session() as session:
        attempt = session.query(SkillAttempt).filter_by(id=attempt_id).with_for_update().one_or_none()
        if attempt is None:
            return None
        if attempt.verification_state in ATTEMPT_TERMINAL:
            return attempt
        from services.live_motion_evidence import is_live_motion
        if is_live_motion(attempt):
            # The existing GPU endpoint grades dice quality, not the published
            # wrist detector's axes. Fail closed instead of certifying another
            # measurement or repeatedly paying for an incompatible scorer.
            attempt.authoritative_score = None
            attempt.tier = None
            attempt.reconciliation = {'reason': 'Live assessment saved for human review; independent score verification is not performed.',
                                      'agreement': 'unverifiable', 'tamper_flag': False}
            transition(session, attempt, 'INSUFFICIENT', {'reason': 'live_assessment_manual_review'})
            _sync_hiring_if_linked(session, attempt)
            session.flush()
            return attempt
        now = _utcnow()
        if attempt.recompute_lease_until and attempt.recompute_lease_until > now:
            raise RecomputeBusy('Assessment processing is already in progress')
        if (attempt.recompute_count or 0) >= MAX_RECOMPUTES:
            attempt.error = 'Processing could not complete after repeated interruptions'
            transition(session, attempt, 'INSUFFICIENT',
                       {'reason': 'processing retry budget exhausted; no skill verdict'})
            _sync_hiring_if_linked(session, attempt)
            session.flush()
            return attempt
        attempt.recompute_lease_id = lease_id
        # Recovery allowance for storage and scoring. This is a lease, not a
        # hard wall-clock cancellation; fencing remains necessary after expiry.
        lease_seconds = max(900, float(os.environ.get('SCORING_TIMEOUT_SEC', '180'))
                            * max(1, int(os.environ.get('SCORING_MAX_RETRIES', '3'))) + 180)
        attempt.recompute_lease_until = now + timedelta(seconds=lease_seconds)
        attempt.dispatch_token = None  # Fence a dispatcher whose HTTP call is still returning.
        attempt.dispatch_due_at = attempt.recompute_lease_until
        transition(session, attempt, "VERIFYING", {"reason": "recompute started"})
        attempt.recompute_count = (attempt.recompute_count or 0) + 1
        count = attempt.recompute_count
        video_url = attempt.video_url
        owner_uid = attempt.user_id
        generation = (attempt.metadata_ or {}).get('recording_generation')
        profile_id = attempt.profile_id
        local_result = attempt.local_block or {}
        on_device = float(attempt.on_device_score) if attempt.on_device_score is not None else None
        session.flush()

    # Phase B: the heavy, networked work (no DB held).
    try:
        if not video_url:
            raise ScoringError("no video uploaded for this attempt")
        vbytes, content_type = fetch_video(video_url, owner_uid=owner_uid, generation=generation)
        server_block = score_video(vbytes, profile_id, content_type=content_type)
    except ScoringError as exc:
        with db_session() as session:
            attempt = session.query(SkillAttempt).filter_by(id=attempt_id).with_for_update().one_or_none()
            if attempt and attempt.verification_state == "VERIFYING" and attempt.recompute_lease_id == lease_id:
                attempt.recompute_lease_id = None
                attempt.recompute_lease_until = None
                attempt.error = str(exc)[:500]
                if count >= MAX_RECOMPUTES:
                    transition(session, attempt, "INSUFFICIENT",
                               {"error": str(exc)[:300], "reason": "scoring unavailable after retries"})
                    _sync_hiring_if_linked(session, attempt)
                else:
                    attempt.updated_at = _utcnow()  # stay VERIFYING; a re-enqueue can retry
                    from services.scoring_dispatch import retry_delay
                    attempt.dispatch_due_at = _utcnow() + timedelta(seconds=retry_delay(count))
                session.flush()
                if attempt.verification_state in ATTEMPT_TERMINAL:
                    return attempt
        log.warning("recompute failed for %s: %s", attempt_id, exc)
        return None

    # Phase C: reconcile + finalize.
    outcome = reconcile(server_block, local_result=local_result, on_device_score=on_device)
    with db_session() as session:
        attempt = session.query(SkillAttempt).filter_by(id=attempt_id).with_for_update().one_or_none()
        if attempt is None or attempt.verification_state in ATTEMPT_TERMINAL:
            return attempt
        if attempt.recompute_lease_id != lease_id:
            return None  # A recovered worker owns the result; stale worker cannot publish.
        attempt.recompute_lease_id = None
        attempt.recompute_lease_until = None
        attempt.server_block = server_block
        attempt.reconciliation = outcome["reconciliation"]
        attempt.authoritative_score = outcome["authoritative_score"]
        attempt.tier = outcome["tier"]
        attempt.error = None
        transition(session, attempt, outcome["state"], {"reconciliation": outcome["reconciliation"]})
        if outcome["state"] == "VERIFIED":
            _stamp_credential(session, attempt)
        _sync_hiring_if_linked(session, attempt)
        session.flush()
        return attempt


def _stamp_credential(session, attempt: SkillAttempt) -> None:
    """Credential eligibility: write the verified score onto the CookProfile. ONLY called
    on VERIFIED. Get-or-create the profile (taking the test is part of the cook application;
    this does NOT grant the cook role — that stays manual approval)."""
    cp = session.get(CookProfile, attempt.user_id)
    if cp is None:
        cp = CookProfile(user_id=attempt.user_id)
        session.add(cp)
    cp.skill_score = attempt.authoritative_score
    cp.skill_verified = True
    cp.skill_tier = attempt.tier
    cp.skill_test_at = _utcnow()
    cp.skill_test_video_url = attempt.video_url or cp.skill_test_video_url
    cp.skill_test_result = {
        "attempt_id": str(attempt.id),
        "authoritative_score": float(attempt.authoritative_score) if attempt.authoritative_score is not None else None,
        "tier": attempt.tier,
        "verification_state": attempt.verification_state,
        "server": attempt.server_block,
        "reconciliation": attempt.reconciliation,
    }


# ── enqueue (Cloud Tasks in prod, inline thread for local dev) ──────────────────

def enqueue_recompute(attempt_id: str, *, dispatch_id: str | None = None) -> str:
    """Dispatch through Cloud Tasks. Failures leave the stored attempt retryable.

    Inline development execution requires SCORING_ALLOW_INLINE=1 and is forbidden
    on Cloud Run. A configured queue outage never falls back to a thread.
    """
    queue = os.environ.get("TASKS_QUEUE", "").strip()
    target = os.environ.get("TASKS_TARGET_URL", "").strip()
    if queue and target:
        try:
            _enqueue_cloud_task(attempt_id, queue, target, dispatch_id=dispatch_id)
            return "cloud_task"
        except Exception:
            log.exception("Cloud Tasks enqueue failed; attempt remains pending")
            raise
    if os.environ.get('SCORING_ALLOW_INLINE') == '1' and not os.environ.get('K_SERVICE'):
        _run_inline(attempt_id)
        return 'inline'
    raise RuntimeError('A durable scoring queue is required')


def _enqueue_cloud_task(attempt_id: str, queue: str, target_url: str, *, dispatch_id=None) -> None:
    """Create an HTTP task that POSTs {attempt_id} to the internal recompute endpoint.
    Retries of one dispatch share a name; recovery uses a fresh dispatch token."""
    from google.cloud import tasks_v2  # lazy import (prod only)
    import json as _json

    client = tasks_v2.CloudTasksClient()
    body = _json.dumps({"attempt_id": attempt_id}).encode()
    task = {
        "name": f"{queue}/tasks/{attempt_id}-{dispatch_id or 'initial'}",
        "dispatch_deadline": {"seconds": 1800},
        "http_request": {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": target_url,
            "headers": {
                "Content-Type": "application/json",
                "X-Internal-Secret": os.environ.get("INTERNAL_SECRET", ""),
            },
            "body": body,
        },
    }
    oidc_sa = os.environ.get("TASKS_OIDC_SA", "").strip()
    if oidc_sa:
        from urllib.parse import urlsplit
        target = urlsplit(target_url)
        audience = os.environ.get('TASKS_OIDC_AUDIENCE') or f'{target.scheme}://{target.netloc}'
        task["http_request"]["oidc_token"] = {"service_account_email": oidc_sa, "audience": audience}
    from google.api_core.exceptions import AlreadyExists
    try:
        client.create_task(request={"parent": queue, "task": task}, retry=None, timeout=30)
    except AlreadyExists:
        pass  # Retrying the same dispatch must not create another scoring job.


def _run_inline(attempt_id: str) -> None:
    """Local/dev fallback: recompute in a daemon thread so /submit returns PROVISIONAL
    immediately. NOT for prod (Cloud Run min-instances=0 can recycle mid-thread — that's
    exactly why Cloud Tasks is used in prod)."""
    def _job():
        try:
            run_recompute(attempt_id)
        except Exception:
            log.exception("inline recompute crashed for %s", attempt_id)
    threading.Thread(target=_job, name=f"recompute-{attempt_id}", daemon=True).start()
