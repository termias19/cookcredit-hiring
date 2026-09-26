BEGIN;

ALTER TABLE orgs ADD COLUMN IF NOT EXISTS stripe_customer_id TEXT;
ALTER TABLE orgs ADD COLUMN IF NOT EXISTS stripe_subscription_id TEXT;
ALTER TABLE orgs ADD COLUMN IF NOT EXISTS subscription_status TEXT;
ALTER TABLE orgs ADD COLUMN IF NOT EXISTS subscription_price_id TEXT;
ALTER TABLE orgs ADD COLUMN IF NOT EXISTS subscription_period_end TIMESTAMPTZ;
ALTER TABLE orgs ADD COLUMN IF NOT EXISTS subscription_cancel_at_period_end BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE orgs ADD COLUMN IF NOT EXISTS billing_updated_at TIMESTAMPTZ;

CREATE UNIQUE INDEX IF NOT EXISTS uq_orgs_stripe_customer
  ON orgs (stripe_customer_id) WHERE stripe_customer_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_orgs_stripe_subscription
  ON orgs (stripe_subscription_id) WHERE stripe_subscription_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS stripe_events (
  id TEXT PRIMARY KEY,
  event_type TEXT NOT NULL,
  livemode BOOLEAN NOT NULL DEFAULT FALSE,
  received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMIT;
