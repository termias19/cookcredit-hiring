-- 006_skill_attempts.sql
-- Dual skill-scoring path: the append-only attempt + transition log.
--
-- An attempt holds the ON-DEVICE (provisional, client-claimed) score and, once the
-- uploaded VIDEO is re-derived by the GPU scorer, the authoritative server block +
-- the reconciliation between them. State advances forward-only:
--   PROVISIONAL -> VERIFYING -> VERIFIED | DISPUTED | INSUFFICIENT
-- A credential is eligible ONLY on VERIFIED. Idempotent on (user_id, session_id):
-- a retried upload/recompute for the same client session never double-scores.
-- (Idempotent DDL: safe to re-run.)

CREATE TABLE IF NOT EXISTS skill_attempts (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id          TEXT NOT NULL,                 -- client-generated UUID (idempotency key)
    profile_id          TEXT NOT NULL DEFAULT 'guillotine_dice',  -- which cut the GPU scores against
    verification_state  TEXT NOT NULL DEFAULT 'PROVISIONAL',      -- PROVISIONAL|VERIFYING|VERIFIED|DISPUTED|INSUFFICIENT
    on_device_score     NUMERIC(5,2),                  -- client-claimed provisional (0..100.00)
    on_device_block     JSONB,                         -- client breakdown (smoothness/consistency/finesse)
    local_score         NUMERIC(5,2),                  -- server recompute from the trajectory (cheap; still forgeable)
    local_block         JSONB,                         -- score_trajectory() output
    server_block        JSONB,                         -- GPU /score response (motion_half, product_half, verdict)
    reconciliation      JSONB,                         -- {agreement, tamper_flag, motion_match, product_score, reason}
    authoritative_score NUMERIC(5,2),                  -- the verified skill number (video-derived) when VERIFIED
    tier                TEXT,                          -- gold | silver | bronze | NULL
    trajectory          JSONB,                         -- captured client trajectory (kept for re-derivation/audit)
    metadata            JSONB,                         -- capture metadata (cut, angle, duration, frames, ...)
    video_url           TEXT,                          -- Firebase Storage URL of the uploaded clip
    error               TEXT,                          -- last recompute error (observability)
    recompute_count     INTEGER NOT NULL DEFAULT 0,    -- recompute tries (idempotent backoff guard)
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_skill_attempts_session UNIQUE (user_id, session_id)
);

-- History (latest-first per user) + the recompute worker's pending scan.
CREATE INDEX IF NOT EXISTS idx_skill_attempts_user_created
    ON skill_attempts (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_skill_attempts_state
    ON skill_attempts (verification_state);

-- Append-only transition log: every state change is a NEW row (never UPDATE/DELETE).
-- This is the audit trail the dual-score design requires; skill_attempts.verification_state
-- is the materialized "current" state, but this table is the source of truth for how it got there.
CREATE TABLE IF NOT EXISTS skill_attempt_events (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    attempt_id  UUID NOT NULL REFERENCES skill_attempts(id) ON DELETE CASCADE,
    from_state  TEXT,                                  -- NULL for the initial PROVISIONAL creation
    to_state    TEXT NOT NULL,
    detail      JSONB,                                 -- why (reconciliation snapshot / error)
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_skill_attempt_events_attempt
    ON skill_attempt_events (attempt_id, created_at);
