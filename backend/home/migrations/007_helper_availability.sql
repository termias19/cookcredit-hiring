-- HOME DATABASE ONLY. Reuse the original availability/blocked-date models.
BEGIN;
DO $$ BEGIN
 IF current_database() !~ '^cookcredit_home_(dev|test|staging|prod)$'
 AND NOT (current_database()='cookcredit_test' AND current_schema() ~ '^home_test_[a-f0-9]+$') THEN
  RAISE EXCEPTION 'Home migration requires a dedicated Home database';
 END IF;
END $$;
ALTER TABLE home_helper_permissions ADD COLUMN IF NOT EXISTS availability_version INTEGER NOT NULL DEFAULT 0;
ALTER TABLE home_helper_permissions ADD COLUMN IF NOT EXISTS availability_time_zone TEXT;
-- The original integer-hour model stops at 23. Home also needs 24 as an end
-- boundary to represent midnight. This changes only Home's dedicated tables;
-- the shared model, Hiring and the retired Mise database remain unchanged.
ALTER TABLE cook_availability DROP CONSTRAINT IF EXISTS cook_availability_end_hour_check;
DO $$ BEGIN
 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='cook_availability'::regclass AND conname='home_availability_end_hour') THEN
  ALTER TABLE cook_availability ADD CONSTRAINT home_availability_end_hour CHECK(end_hour BETWEEN 0 AND 24);
 END IF;
END $$;
COMMIT;
