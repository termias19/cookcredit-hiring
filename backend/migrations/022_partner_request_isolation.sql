BEGIN;

ALTER TABLE role_postings
  ADD COLUMN IF NOT EXISTS integration_environment TEXT NOT NULL DEFAULT 'live';
ALTER TABLE partner_invitations
  ADD COLUMN IF NOT EXISTS request_fingerprint TEXT,
  ADD COLUMN IF NOT EXISTS request_config JSONB;
ALTER TABLE partner_webhooks
  ADD COLUMN IF NOT EXISTS environment TEXT NOT NULL DEFAULT 'live';

-- Preserve the current configuration for pre-release invitations. Earlier versions
-- did not retain historical questions, so only their current settings are recoverable.
UPDATE partner_invitations i
SET request_config = jsonb_build_object(
  'applicationQuestions', COALESCE(r.requirements->'applicationQuestions', '[]'::jsonb),
  'locationLabel', r.requirements->'locationLabel')
FROM role_postings r
WHERE r.id = i.role_posting_id AND i.request_config IS NULL;

-- A pre-release test-only role can be classified safely. Refuse to silently
-- reclassify applications if an older installation mixed live and test invitations.
UPDATE role_postings r SET integration_environment = 'test'
WHERE r.integration_managed AND EXISTS (
  SELECT 1 FROM partner_invitations i WHERE i.role_posting_id = r.id AND i.environment = 'test'
) AND NOT EXISTS (
  SELECT 1 FROM partner_invitations i WHERE i.role_posting_id = r.id AND i.environment = 'live'
);
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM partner_invitations i JOIN role_postings r ON r.id = i.role_posting_id
             WHERE i.environment <> r.integration_environment) THEN
    RAISE EXCEPTION 'Mixed test/live roles found. Separate those pre-release applications before migration 022.';
  END IF;
END $$;

DROP INDEX IF EXISTS uq_role_postings_org_external_job;
CREATE UNIQUE INDEX IF NOT EXISTS uq_role_postings_environment_external_job
  ON role_postings (org_id, integration_environment, external_job_id)
  WHERE external_job_id IS NOT NULL;

-- Support both the original SQL indexes and ORM-created constraints.
ALTER TABLE partner_invitations DROP CONSTRAINT IF EXISTS uq_partner_invitation_idempotency;
DROP INDEX IF EXISTS uq_partner_invitation_idempotency;
CREATE UNIQUE INDEX IF NOT EXISTS uq_partner_invitation_environment_idempotency
  ON partner_invitations (org_id, environment, idempotency_key);
ALTER TABLE partner_webhooks DROP CONSTRAINT IF EXISTS uq_partner_webhook_org_url;
DROP INDEX IF EXISTS uq_partner_webhook_org_url;
CREATE UNIQUE INDEX IF NOT EXISTS uq_partner_webhook_environment_url
  ON partner_webhooks (org_id, environment, url);

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'role_integration_environment_check'
                 AND conrelid = 'role_postings'::regclass) THEN
    ALTER TABLE role_postings ADD CONSTRAINT role_integration_environment_check
      CHECK (integration_environment IN ('test', 'live'));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'partner_webhook_environment_check'
                 AND conrelid = 'partner_webhooks'::regclass) THEN
    ALTER TABLE partner_webhooks ADD CONSTRAINT partner_webhook_environment_check
      CHECK (environment IN ('test', 'live'));
  END IF;
END $$;

COMMIT;
