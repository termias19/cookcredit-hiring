-- Cook application funnel: track when a cook submits their application so the
-- client can distinguish none / pending / approved. Approval stays manual
-- (team review) via the existing cook_profiles.approved flag.
-- Apply with:  psql "$DATABASE_URL" -f migrations/004_cook_application.sql

BEGIN;

ALTER TABLE cook_profiles ADD COLUMN IF NOT EXISTS applied_at timestamptz;

-- Find pending applications quickly (the team review queue).
CREATE INDEX IF NOT EXISTS idx_cook_pending
  ON cook_profiles (applied_at)
  WHERE applied_at IS NOT NULL AND approved = false;

COMMIT;
