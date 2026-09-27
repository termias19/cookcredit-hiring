-- Included access is explicitly preserved during rollout before billing is enabled.
ALTER TABLE orgs ADD COLUMN IF NOT EXISTS included_access BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE orgs ADD COLUMN IF NOT EXISTS subscription_limits JSONB;
CREATE TABLE IF NOT EXISTS hiring_prices (
 id UUID PRIMARY KEY, plan TEXT NOT NULL CHECK (plan IN ('team','integration')),
 interval TEXT NOT NULL CHECK (interval IN ('month','year')),
 currency TEXT NOT NULL CHECK (currency = 'usd'), amount INTEGER NOT NULL CHECK (amount BETWEEN 100 AND 10000000),
 limits JSONB NOT NULL, state TEXT NOT NULL DEFAULT 'draft' CHECK (state IN ('draft','published')),
 active BOOLEAN NOT NULL DEFAULT FALSE, stripe_price_id TEXT UNIQUE, previous_id UUID,
 created_by TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS hiring_prices_current ON hiring_prices(plan, interval) WHERE active;
CREATE INDEX IF NOT EXISTS hiring_prices_history ON hiring_prices(created_at DESC, id);
