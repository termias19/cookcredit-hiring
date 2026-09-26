BEGIN;

-- External ATS jobs reuse the existing role/application/assessment pipeline.  These
-- fields distinguish the hidden integration-managed role from a role created in Mise.
ALTER TABLE role_postings
  ADD COLUMN IF NOT EXISTS external_job_id TEXT,
  ADD COLUMN IF NOT EXISTS integration_managed BOOLEAN NOT NULL DEFAULT FALSE;

CREATE UNIQUE INDEX IF NOT EXISTS uq_role_postings_org_external_job
  ON role_postings (org_id, external_job_id)
  WHERE external_job_id IS NOT NULL;

ALTER TABLE partner_api_keys
  ADD COLUMN IF NOT EXISTS environment TEXT NOT NULL DEFAULT 'live';

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'partner_api_key_environment_check'
  ) THEN
    ALTER TABLE partner_api_keys ADD CONSTRAINT partner_api_key_environment_check
      CHECK (environment IN ('test','live'));
  END IF;
END $$;

-- partner_invitations is the durable assessment request.  The original invitation
-- endpoint remains compatible while the universal API adds the fields below.
ALTER TABLE partner_invitations
  ADD COLUMN IF NOT EXISTS external_job_id TEXT,
  ADD COLUMN IF NOT EXISTS job_title TEXT,
  ADD COLUMN IF NOT EXISTS assessment_profile TEXT NOT NULL DEFAULT 'guillotine_dice',
  ADD COLUMN IF NOT EXISTS assessment_profile_version TEXT NOT NULL DEFAULT 'knife-dice-v1',
  ADD COLUMN IF NOT EXISTS attempt_limit INTEGER NOT NULL DEFAULT 3,
  ADD COLUMN IF NOT EXISTS return_url TEXT,
  ADD COLUMN IF NOT EXISTS environment TEXT NOT NULL DEFAULT 'live',
  ADD COLUMN IF NOT EXISTS canceled_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS review_decision TEXT,
  ADD COLUMN IF NOT EXISTS review_reason TEXT,
  ADD COLUMN IF NOT EXISTS reviewed_by TEXT REFERENCES users(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'partner_invitation_attempt_limit_check'
  ) THEN
    ALTER TABLE partner_invitations ADD CONSTRAINT partner_invitation_attempt_limit_check
      CHECK (attempt_limit BETWEEN 1 AND 3);
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'partner_invitation_environment_check'
  ) THEN
    ALTER TABLE partner_invitations ADD CONSTRAINT partner_invitation_environment_check
      CHECK (environment IN ('test','live'));
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'partner_invitation_review_decision_check'
  ) THEN
    ALTER TABLE partner_invitations ADD CONSTRAINT partner_invitation_review_decision_check
      CHECK (review_decision IS NULL OR review_decision IN ('advance','hold','decline'));
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_partner_invitations_org_external_job
  ON partner_invitations (org_id, external_job_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_partner_invitations_org_external_candidate
  ON partner_invitations (org_id, external_candidate_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_partner_invitations_org_status
  ON partner_invitations (org_id, status, created_at DESC);

COMMIT;
