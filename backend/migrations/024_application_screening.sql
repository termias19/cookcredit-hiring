ALTER TABLE hiring_applications ADD COLUMN IF NOT EXISTS assessment_criteria JSONB;
ALTER TABLE hiring_applications ADD COLUMN IF NOT EXISTS screening_result JSONB;
ALTER TABLE hiring_applications ADD COLUMN IF NOT EXISTS screening_outcome TEXT;
CREATE INDEX IF NOT EXISTS idx_hiring_screening_page
ON hiring_applications(role_posting_id, screening_outcome, submitted_at DESC, id DESC);
