ALTER TABLE account_emails ADD COLUMN IF NOT EXISTS content JSONB;
CREATE INDEX IF NOT EXISTS idx_account_emails_kind_status ON account_emails(kind, status);
ALTER TABLE account_emails DROP CONSTRAINT IF EXISTS account_emails_kind_check;
ALTER TABLE account_emails ADD CONSTRAINT account_emails_kind_check CHECK
 (kind IN ('verify','welcome','reset','access_requested','access_approved','workspace_invite','billing_paid','billing_failed','campaign'));

CREATE TABLE IF NOT EXISTS hiring_email_preferences (
 user_id TEXT PRIMARY KEY REFERENCES users(id),
 email TEXT NOT NULL,
 opted_in BOOLEAN NOT NULL DEFAULT false,
 consent_version TEXT NOT NULL DEFAULT 'hiring-offers-v1',
 updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 unsubscribe_token TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS hiring_campaigns (
 id UUID PRIMARY KEY,
 subject TEXT NOT NULL,
 body TEXT NOT NULL,
 postal_address TEXT NOT NULL DEFAULT '',
 status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','scheduled','paused','trashed','complete')),
 interval_days INTEGER NOT NULL DEFAULT 0 CHECK(interval_days IN (0,7,30)),
 next_run_at TIMESTAMPTZ,
 run_at TIMESTAMPTZ,
 cursor TEXT,
 revision INTEGER NOT NULL DEFAULT 1,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_hiring_campaigns_due ON hiring_campaigns(next_run_at) WHERE status='scheduled';
CREATE TABLE IF NOT EXISTS hiring_campaign_events (
 id UUID PRIMARY KEY,
 campaign_id UUID NOT NULL REFERENCES hiring_campaigns(id),
 actor_id TEXT NOT NULL,
 action TEXT NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
