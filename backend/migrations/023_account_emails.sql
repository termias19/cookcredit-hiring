CREATE TABLE IF NOT EXISTS account_emails (
    id UUID PRIMARY KEY,
    dedupe_key TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL CHECK (kind IN ('verify', 'welcome', 'reset')),
    recipient TEXT NOT NULL,
    user_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','sending','sent','skipped','failed')),
    attempts INTEGER NOT NULL DEFAULT 0,
    available_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    lease_until TIMESTAMPTZ,
    lease_token UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    last_error TEXT
);
CREATE INDEX IF NOT EXISTS idx_account_emails_pending ON account_emails(available_at)
    WHERE status IN ('pending','sending');
