"""Unit tests for the dual skill-scoring path: the reconciliation decision logic and
the append-only state machine. These are pure (no DB) and cover the tamper / verdict
branches that decide whether a credential is issued.
"""
import os
import types

import pytest

from models import is_valid_transition, ATTEMPT_STATES
from services import skill_attempts as sa


# ── helpers to build a GPU /score-shaped server_block (mirrors serving/score_service) ──

def _server(*, technique="guillotine", candidate="guillotine", motion_low_calib=False,
            product_ok=True, composite=0.82, technique_ok=True, is_dice=True):
    motion = {"technique": technique, "candidate": candidate,
              "confidence": 0.8, "low_calibration": motion_low_calib, "scores": {}}
    product = ({"ok": True, "composite": composite, "is_dice": is_dice,
                "measurement": {"n_pieces": 40}}
               if product_ok else
               {"ok": False, "evidence": "INSUFFICIENT", "reason": "no measurable diced frame."})
    return {
        "profile_id": "guillotine_dice",
        "motion_half": motion,
        "technique_match": technique_ok,
        "product_half": product,
        "verdict": {
            "technique_ok": technique_ok,
            "is_dice": (is_dice if product_ok else None),
            "product_score": (composite if product_ok else None),
            "summary": "Valid guillotine dice." if (technique_ok and product_ok) else "n/a",
        },
    }


def _local(*, candidate="guillotine", verified=True, low_calib=False):
    return {"ok": True, "verified": verified, "skill_score": 80.0,
            "technique": {"candidate": candidate, "technique": candidate,
                          "low_calibration": low_calib, "confidence": 0.7}}


# ── _scale_product ────────────────────────────────────────────────────────────

def test_scale_product_normalizes_unit_interval():
    assert sa._scale_product(0.82) == 82.0
    assert sa._scale_product(0.0) == 0.0


def test_scale_product_passes_through_0_100_and_clamps():
    # Composite is documented 0..1 (so 0.82 -> 82). A value already in (1, 100] is
    # treated as an already-scaled score; anything over 100 clamps.
    assert sa._scale_product(82) == 82.0
    assert sa._scale_product(150) == 100.0
    assert sa._scale_product(-3) == 0.0
    assert sa._scale_product(None) is None
    assert sa._scale_product("x") is None


# ── reconcile: the verdict / tamper decision table ──────────────────────────────

def test_verified_when_video_confirms_technique_and_pieces_gradeable():
    out = sa.reconcile(_server(composite=0.82), local_result=_local(), on_device_score=88)
    assert out["state"] == "VERIFIED"
    assert out["authoritative_score"] == 82.0
    assert out["tier"] == "gold"                  # 82 >= 82 gold threshold
    assert out["reconciliation"]["tamper_flag"] is False
    assert out["reconciliation"]["agreement"] == "match"
    assert out["reconciliation"]["comparable_numeric"] is False


def test_disputed_when_no_chop_in_video_but_strong_claim():
    # Tamper: client claims a passing chop, the video has no detectable chopping.
    srv = _server(technique="uncertain", candidate=None)
    out = sa.reconcile(srv, local_result=_local(verified=True), on_device_score=92)
    assert out["state"] == "DISPUTED"
    assert out["reconciliation"]["tamper_flag"] is True
    assert out["authoritative_score"] is None


def test_disputed_when_technique_mismatch():
    # Client claimed guillotine, the video shows rock_chop (both confident) -> lie.
    srv = _server(technique="rock_chop", candidate="rock_chop")
    out = sa.reconcile(srv, local_result=_local(candidate="guillotine"), on_device_score=80)
    assert out["state"] == "DISPUTED"
    assert out["reconciliation"]["tamper_flag"] is True
    assert out["reconciliation"]["technique_video"] == "rock_chop"
    assert out["reconciliation"]["technique_claimed"] == "guillotine"


def test_insufficient_when_motion_uncertain_and_no_strong_claim():
    # Genuine bad capture (not a lie): no chop detected, client didn't overclaim.
    srv = _server(technique="uncertain", candidate=None)
    out = sa.reconcile(srv, local_result=_local(verified=False), on_device_score=10)
    assert out["state"] == "INSUFFICIENT"
    assert out["reconciliation"]["tamper_flag"] is False


def test_insufficient_when_wrong_technique_for_cut():
    srv = _server(technique_ok=False)
    out = sa.reconcile(srv, local_result=_local(), on_device_score=70)
    assert out["state"] == "INSUFFICIENT"
    assert out["reconciliation"]["tamper_flag"] is False


def test_insufficient_when_pieces_not_gradeable():
    srv = _server(product_ok=False)
    out = sa.reconcile(srv, local_result=_local(), on_device_score=70)
    assert out["state"] == "INSUFFICIENT"
    assert out["authoritative_score"] is None


def test_verified_tiers_track_thresholds():
    assert sa.reconcile(_server(composite=0.70), local_result=_local(),
                        on_device_score=70)["tier"] == "silver"
    assert sa.reconcile(_server(composite=0.58), local_result=_local(),
                        on_device_score=60)["tier"] == "bronze"


# ── state machine ───────────────────────────────────────────────────────────────

def test_valid_transitions():
    assert is_valid_transition("PROVISIONAL", "VERIFYING")
    assert is_valid_transition("PROVISIONAL", "INSUFFICIENT")
    assert is_valid_transition("VERIFYING", "VERIFIED")
    assert is_valid_transition("VERIFYING", "DISPUTED")
    assert is_valid_transition("VERIFYING", "VERIFYING")   # idempotent recompute retry


def test_terminal_states_are_final():
    for term in ("VERIFIED", "DISPUTED", "INSUFFICIENT"):
        for nxt in ATTEMPT_STATES:
            assert not is_valid_transition(term, nxt)


def test_unknown_states_rejected():
    assert not is_valid_transition("PROVISIONAL", "BOGUS")
    assert not is_valid_transition("NOPE", "VERIFIED")


def test_transition_appends_event_and_advances():
    added = []
    fake_session = types.SimpleNamespace(add=lambda x: added.append(x))
    attempt = types.SimpleNamespace(id="a1", verification_state="PROVISIONAL", updated_at=None)
    sa.transition(fake_session, attempt, "VERIFYING", {"reason": "go"})
    assert attempt.verification_state == "VERIFYING"
    assert len(added) == 1 and added[0].to_state == "VERIFYING" and added[0].from_state == "PROVISIONAL"


def test_transition_rejects_illegal_move():
    fake_session = types.SimpleNamespace(add=lambda x: None)
    attempt = types.SimpleNamespace(id="a1", verification_state="VERIFIED", updated_at=None)
    with pytest.raises(ValueError):
        sa.transition(fake_session, attempt, "PROVISIONAL", None)


# ── DB-gated: idempotency (only runs if a test Postgres is configured) ───────────

@pytest.mark.skipif(not os.environ.get("DATABASE_URL"),
                    reason="needs a Postgres (set DATABASE_URL) for the attempt-store tests")
def test_create_or_get_attempt_is_idempotent_on_session_id():
    from services.database import db_session, init_db
    init_db()
    from models import User
    uid, sid = "test-user-idem", "sess-" + os.urandom(4).hex()
    # skill_attempts.user_id is a FK to users (enforced on a real Postgres), so the user must exist.
    with db_session() as s:
        if s.get(User, uid) is None:
            s.add(User(id=uid, email=f"{uid}@test.com", name="Idem Test", roles=["eater"], active_role="eater"))
    try:
        with db_session() as s:
            a1, created1 = sa.create_or_get_attempt(
                s, user_id=uid, session_id=sid, profile_id="guillotine_dice",
                on_device_score=80, on_device_block={}, local_result=_local(),
                trajectory=[], metadata={}, video_url=None)
            assert created1 is True
            first_id = str(a1.id)
        with db_session() as s:
            a2, created2 = sa.create_or_get_attempt(
                s, user_id=uid, session_id=sid, profile_id="guillotine_dice",
                on_device_score=80, on_device_block={}, local_result=_local(),
                trajectory=[], metadata={}, video_url="http://x/clip.webm")
            assert created2 is False
            assert str(a2.id) == first_id
            assert a2.video_url == "http://x/clip.webm"   # backfilled on retry
    finally:
        with db_session() as s:
            u = s.get(User, uid)
            if u:
                s.delete(u)


# ── upload-object naming: session ids must be safe as storage object names ───────
def test_safe_session_name_accepts_uuids_and_slugs():
    from routes.skills import _safe_session_name
    assert _safe_session_name("0b654d29-9f00-4a6b-8f6e-1c2d3e4f5a6b") == "0b654d29-9f00-4a6b-8f6e-1c2d3e4f5a6b"
    assert _safe_session_name("abc123XYZ_-") == "abc123XYZ_-"


def test_safe_session_name_rejects_traversal_and_junk():
    from routes.skills import _safe_session_name
    for bad in (None, "", "short", "a" * 65, "../../etc/passwd", "x/y", "a.b.webm", "a b c d e f"):
        assert _safe_session_name(bad) is None
