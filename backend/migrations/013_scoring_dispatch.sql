BEGIN;
ALTER TABLE skill_attempts ADD COLUMN IF NOT EXISTS dispatch_due_at TIMESTAMPTZ;
ALTER TABLE skill_attempts ADD COLUMN IF NOT EXISTS dispatch_token UUID;
ALTER TABLE skill_attempts ADD COLUMN IF NOT EXISTS dispatch_failures INTEGER NOT NULL DEFAULT 0;
CREATE INDEX IF NOT EXISTS idx_skill_attempts_dispatch_due
    ON skill_attempts(dispatch_due_at, id)
    WHERE verification_state IN ('PROVISIONAL', 'VERIFYING') AND dispatch_due_at IS NOT NULL;
-- Resume only recordings whose generation was pinned at submission. Historical
-- unpinned records require separate review, never inference against a replacement.
UPDATE skill_attempts SET dispatch_due_at = NOW()
    WHERE verification_state IN ('PROVISIONAL', 'VERIFYING')
      AND video_url IS NOT NULL AND metadata->>'recording_generation' IS NOT NULL
      AND dispatch_due_at IS NULL;
COMMIT;
