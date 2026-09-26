-- Owner-reviewed access is persistent data, not a deployment-time tester list.
CREATE TABLE IF NOT EXISTS hiring_access_requests (
 id UUID PRIMARY KEY,
 email TEXT NOT NULL UNIQUE,
 name TEXT NOT NULL DEFAULT '',
 company TEXT NOT NULL DEFAULT '',
 message TEXT NOT NULL DEFAULT '',
 source TEXT NOT NULL CHECK (source IN ('website','inbox','owner')),
 status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','declined','revoked')),
 revision INTEGER NOT NULL DEFAULT 0,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 decided_by TEXT,
 decided_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_hiring_access_queue ON hiring_access_requests(status, created_at, id);
CREATE TABLE IF NOT EXISTS hiring_access_events (
 id UUID PRIMARY KEY,
 request_id UUID NOT NULL REFERENCES hiring_access_requests(id),
 actor_id TEXT,
 action TEXT NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS hiring_access_inbox (
 id TEXT PRIMARY KEY,
 uid_validity TEXT,
 last_uid BIGINT NOT NULL DEFAULT 0,
 checked_at TIMESTAMPTZ,
 last_error TEXT
);
ALTER TABLE account_emails ADD COLUMN IF NOT EXISTS access_request_id UUID REFERENCES hiring_access_requests(id);
ALTER TABLE account_emails ADD COLUMN IF NOT EXISTS access_revision INTEGER;
ALTER TABLE account_emails DROP CONSTRAINT IF EXISTS account_emails_kind_check;
ALTER TABLE account_emails ADD CONSTRAINT account_emails_kind_check
 CHECK (kind IN ('verify','welcome','reset','access_requested','access_approved'));
