-- 005_assessments.sql
-- Standalone knife-skill assessments — the graded-assessment product.
-- Decoupled from cook_profiles: any user can be graded and keep a history.
-- This is the product's system of record + the demonstration-data flywheel.
-- (Idempotent: safe to re-run.)

CREATE TABLE IF NOT EXISTS assessments (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL DEFAULT 'technique',   -- technique | fused
    skill_score NUMERIC(5,2),                         -- 0..100.00; NULL when unscorable
    verified    BOOLEAN NOT NULL DEFAULT FALSE,
    tier        TEXT,                                 -- gold | silver | bronze | NULL
    result      JSONB,                                -- full scoring breakdown + capture metadata
    video_url   TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- History (latest-first per user) + freemium counting.
CREATE INDEX IF NOT EXISTS idx_assessments_user_created
    ON assessments (user_id, created_at DESC);
