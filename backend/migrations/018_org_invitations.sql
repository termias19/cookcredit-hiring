BEGIN;

CREATE TABLE IF NOT EXISTS org_invitations (
  id UUID PRIMARY KEY,
  org_id UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  invited_email TEXT NOT NULL,
  seat_role TEXT NOT NULL CHECK (seat_role IN ('admin','recruiter','hiring_manager','viewer')),
  token_hash TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','accepted','revoked','expired')),
  invited_by TEXT REFERENCES users(id) ON DELETE SET NULL,
  accepted_by TEXT REFERENCES users(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  expires_at TIMESTAMPTZ NOT NULL,
  accepted_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_org_invitations_org_status
  ON org_invitations (org_id, status, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_org_pending_invitation_email
  ON org_invitations (org_id, lower(invited_email)) WHERE status = 'pending';

COMMIT;
