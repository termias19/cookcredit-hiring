-- Additive processing state on the existing attempt, independent of scoring.
-- No media, consent, assessment history or existing scoring state is changed.
ALTER TABLE skill_attempts ADD COLUMN IF NOT EXISTS compression_state TEXT;
ALTER TABLE skill_attempts ADD COLUMN IF NOT EXISTS compression_due_at TIMESTAMPTZ;
ALTER TABLE skill_attempts ADD COLUMN IF NOT EXISTS compression_lease_id UUID;
ALTER TABLE skill_attempts ADD COLUMN IF NOT EXISTS compression_lease_until TIMESTAMPTZ;
ALTER TABLE skill_attempts ADD COLUMN IF NOT EXISTS compression_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE skill_attempts ADD COLUMN IF NOT EXISTS compression_error TEXT;
ALTER TABLE skill_attempts ADD COLUMN IF NOT EXISTS compression_requested_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS idx_skill_attempts_compression_due
    ON skill_attempts(compression_due_at, id)
    WHERE compression_state IN ('pending', 'running');
CREATE INDEX IF NOT EXISTS idx_skill_attempts_compression_new
    ON skill_attempts(created_at, id)
    WHERE compression_state IS NULL AND metadata->>'source' = 'cookcredit-skill-live';
