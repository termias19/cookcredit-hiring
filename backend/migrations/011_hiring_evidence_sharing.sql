-- No grants are backfilled: a pipeline relationship is not applicant consent.
BEGIN;
CREATE TABLE IF NOT EXISTS assessment_shares (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    role_posting_id UUID NOT NULL REFERENCES role_postings(id) ON DELETE CASCADE,
    attempt_id UUID NOT NULL REFERENCES skill_attempts(id) ON DELETE CASCADE,
    applicant_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    storage_path TEXT NOT NULL,
    storage_generation TEXT NOT NULL,
    consent_version TEXT NOT NULL,
    granted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at TIMESTAMPTZ,
    CONSTRAINT uq_assessment_share UNIQUE (role_posting_id, attempt_id)
);
CREATE INDEX IF NOT EXISTS idx_assessment_shares_applicant
    ON assessment_shares(applicant_id, granted_at DESC);
CREATE TABLE IF NOT EXISTS assessment_access_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    share_id UUID NOT NULL REFERENCES assessment_shares(id) ON DELETE CASCADE,
    viewer_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    accessed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_assessment_access_share ON assessment_access_log(share_id, accessed_at);
COMMIT;
