-- 002_skill_test.sql
-- Cook chopping skill-test gate: extra columns on cook_profiles.
-- (skill_score + skill_verified already exist from 001_initial.sql.)
-- Apply:  psql "$DATABASE_URL" -f migrations/002_skill_test.sql

ALTER TABLE cook_profiles
  ADD COLUMN IF NOT EXISTS skill_tier            TEXT,
  ADD COLUMN IF NOT EXISTS skill_test_at         TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS skill_test_video_url  TEXT,
  ADD COLUMN IF NOT EXISTS skill_test_result     JSONB;
