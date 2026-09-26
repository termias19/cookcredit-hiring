BEGIN;
ALTER TABLE skill_attempts ADD COLUMN IF NOT EXISTS recompute_lease_id UUID;
ALTER TABLE skill_attempts ADD COLUMN IF NOT EXISTS recompute_lease_until TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS idx_skill_attempts_pending_lease
    ON skill_attempts(verification_state, recompute_lease_until, updated_at)
    WHERE verification_state IN ('PROVISIONAL', 'VERIFYING');
COMMIT;
