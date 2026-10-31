-- HOME DATABASE ONLY. Draft edits never activate business commitments.
BEGIN;
DO $$ BEGIN
 IF current_database() !~ '^cookcredit_home_(dev|test|staging|prod)$'
 AND NOT (current_database()='cookcredit_test' AND current_schema() ~ '^home_test_[a-f0-9]+$') THEN
  RAISE EXCEPTION 'Home migration requires a dedicated Home database';
 END IF;
END $$;
ALTER TABLE home_operating_rules ADD COLUMN IF NOT EXISTS active_version INTEGER;
ALTER TABLE home_operating_rules ADD COLUMN IF NOT EXISTS active_settings JSONB;
ALTER TABLE home_operating_rules ADD COLUMN IF NOT EXISTS activated_at TIMESTAMPTZ;
ALTER TABLE home_operating_rules ADD COLUMN IF NOT EXISTS activated_by TEXT REFERENCES users(id);
DO $$ BEGIN
 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='home_operating_rules'::regclass AND conname='home_active_policy_complete') THEN
  ALTER TABLE home_operating_rules ADD CONSTRAINT home_active_policy_complete CHECK (
   (active_version IS NULL AND active_settings IS NULL AND activated_at IS NULL AND activated_by IS NULL)
   OR (active_version IS NOT NULL AND active_settings IS NOT NULL
       AND active_version>0 AND active_version<=version AND jsonb_typeof(active_settings)='object'
       AND activated_at IS NOT NULL AND activated_by IS NOT NULL));
 END IF;
END $$;
-- No activation, hours, helper coverage or public booking access is seeded.
-- Late physical completion can matter after the planned date has passed.
CREATE INDEX IF NOT EXISTS home_bookings_recent_completion
 ON bookings(completed_at,cook_id)
 WHERE completed_at IS NOT NULL AND status<>'cancelled';
COMMIT;
