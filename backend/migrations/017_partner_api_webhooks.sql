BEGIN;

CREATE TABLE IF NOT EXISTS partner_api_keys (
  id UUID PRIMARY KEY,
  org_id UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  key_prefix TEXT NOT NULL UNIQUE,
  secret_hash TEXT NOT NULL UNIQUE,
  scopes TEXT[] NOT NULL DEFAULT '{}',
  created_by TEXT REFERENCES users(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_used_at TIMESTAMPTZ,
  expires_at TIMESTAMPTZ,
  revoked_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_partner_api_keys_org ON partner_api_keys (org_id, created_at);

CREATE TABLE IF NOT EXISTS partner_invitations (
  id UUID PRIMARY KEY,
  org_id UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  role_posting_id UUID NOT NULL REFERENCES role_postings(id) ON DELETE CASCADE,
  token_hash TEXT NOT NULL UNIQUE,
  token_ciphertext TEXT NOT NULL,
  candidate_email TEXT NOT NULL,
  external_candidate_id TEXT,
  idempotency_key TEXT NOT NULL,
  application_id UUID REFERENCES hiring_applications(id) ON DELETE SET NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  expires_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  accepted_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_partner_invitation_idempotency
  ON partner_invitations (org_id, idempotency_key);
CREATE INDEX IF NOT EXISTS idx_partner_invitations_org_created ON partner_invitations (org_id, created_at);

CREATE TABLE IF NOT EXISTS partner_webhooks (
  id UUID PRIMARY KEY,
  org_id UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  url TEXT NOT NULL,
  event_types TEXT[] NOT NULL DEFAULT '{}',
  secret_ciphertext TEXT NOT NULL,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  failure_count INTEGER NOT NULL DEFAULT 0,
  disabled_at TIMESTAMPTZ,
  created_by TEXT REFERENCES users(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_partner_webhook_org_url UNIQUE (org_id, url)
);

CREATE TABLE IF NOT EXISTS partner_webhook_deliveries (
  id UUID PRIMARY KEY,
  webhook_id UUID NOT NULL REFERENCES partner_webhooks(id) ON DELETE CASCADE,
  event_id UUID NOT NULL,
  event_type TEXT NOT NULL,
  payload JSONB NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  attempts INTEGER NOT NULL DEFAULT 0,
  next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  lock_token UUID,
  locked_until TIMESTAMPTZ,
  delivered_at TIMESTAMPTZ,
  last_error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_partner_webhook_delivery_event UNIQUE (webhook_id, event_id)
);
CREATE INDEX IF NOT EXISTS idx_partner_webhook_delivery_due
  ON partner_webhook_deliveries (status, next_attempt_at);

COMMIT;
