-- 007_admin_review.sql
-- Admin review of cook applications: a rejection timestamp + a free-text review note
-- so the application queue can represent approved | rejected | pending | none.
-- (Idempotent: safe to re-run.)

ALTER TABLE cook_profiles ADD COLUMN IF NOT EXISTS rejected_at TIMESTAMPTZ;
ALTER TABLE cook_profiles ADD COLUMN IF NOT EXISTS review_note TEXT;
