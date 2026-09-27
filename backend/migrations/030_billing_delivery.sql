BEGIN;
ALTER TABLE orgs ADD COLUMN IF NOT EXISTS billing_checkout JSONB;
ALTER TABLE stripe_events ALTER COLUMN processed_at DROP NOT NULL;
ALTER TABLE stripe_events ADD COLUMN IF NOT EXISTS payload JSONB;
ALTER TABLE stripe_events ADD COLUMN IF NOT EXISTS attempts INTEGER NOT NULL DEFAULT 0;
ALTER TABLE stripe_events ADD COLUMN IF NOT EXISTS next_attempt_at TIMESTAMPTZ;
ALTER TABLE stripe_events ADD COLUMN IF NOT EXISTS last_error TEXT;
CREATE INDEX IF NOT EXISTS idx_stripe_events_pending
    ON stripe_events(next_attempt_at, id) WHERE processed_at IS NULL;
COMMIT;
