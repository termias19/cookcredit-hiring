-- Separate Home database; no live money or external requests during migrations.
BEGIN;
DO $$ BEGIN
 IF current_database() !~ '^cookcredit_home_(dev|test|staging|prod)$'
 AND NOT (current_database()='cookcredit_test' AND current_schema() ~ '^home_test_[a-f0-9]+$') THEN
  RAISE EXCEPTION 'Home migration requires a dedicated Home database';
 END IF;
END $$;
ALTER TABLE home_visits ADD COLUMN IF NOT EXISTS customer_confirmed_at TIMESTAMPTZ;
INSERT INTO users(id,email,name,roles,active_role) VALUES
 ('system:home','home-system@cookcredit.invalid','CookCredit system','{}','eater') ON CONFLICT DO NOTHING;
DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_constraint WHERE conrelid='home_quote_approvals'::regclass AND conname='home_approval_customer_key') THEN
  ALTER TABLE home_quote_approvals ADD CONSTRAINT home_approval_customer_key UNIQUE(quote_id,customer_id);
 END IF;
 IF NOT EXISTS(SELECT 1 FROM pg_constraint WHERE conrelid='home_quote_helper_acceptances'::regclass AND conname='home_acceptance_helper_key') THEN
  ALTER TABLE home_quote_helper_acceptances ADD CONSTRAINT home_acceptance_helper_key UNIQUE(quote_id,helper_id);
 END IF;
END $$;
CREATE TABLE IF NOT EXISTS home_payments (
 id UUID PRIMARY KEY, booking_id UUID NOT NULL REFERENCES home_visits(booking_id),
 quote_id UUID NOT NULL UNIQUE REFERENCES home_quote_approvals(quote_id),
 customer_id TEXT NOT NULL REFERENCES users(id), helper_id TEXT NOT NULL REFERENCES users(id),
 amount_cents INTEGER NOT NULL CHECK(amount_cents>0), refunded_cents INTEGER NOT NULL DEFAULT 0,
 status TEXT NOT NULL CHECK(status IN ('creating','open','processing','paid','expired','cancel_pending','cancelled','refunded','review_required')),
 livemode BOOLEAN NOT NULL, checkout_attempt INTEGER NOT NULL DEFAULT 1 CHECK(checkout_attempt>0),
 checkout_id TEXT UNIQUE, checkout_url TEXT, payment_intent_id TEXT UNIQUE, charge_id TEXT,
 paid_at TIMESTAMPTZ, disputed BOOLEAN NOT NULL DEFAULT false,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 CHECK(refunded_cents BETWEEN 0 AND amount_cents),
 FOREIGN KEY(booking_id,quote_id) REFERENCES home_quotes(booking_id,id),
 FOREIGN KEY(quote_id,customer_id) REFERENCES home_quote_approvals(quote_id,customer_id),
 FOREIGN KEY(quote_id,helper_id) REFERENCES home_quote_helper_acceptances(quote_id,helper_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS home_payment_active_booking ON home_payments(booking_id)
 WHERE status NOT IN ('expired','cancelled','refunded');
CREATE TABLE IF NOT EXISTS home_financial_operations (
 id UUID PRIMARY KEY, booking_id UUID REFERENCES home_visits(booking_id),
 payment_id UUID REFERENCES home_payments(id), actor_id TEXT NOT NULL REFERENCES users(id),
 kind TEXT NOT NULL CHECK(kind IN ('checkout','expire','refund_unused','refund_cancel','transfer','reverse','connect')),
 dedupe_key TEXT UNIQUE NOT NULL, payload JSONB NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','running','succeeded','retry','held','review_required','cancelled')),
 provider_id TEXT, attempts INTEGER NOT NULL DEFAULT 0, available_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 first_started_at TIMESTAMPTZ, lease_until TIMESTAMPTZ, lease_token UUID, last_error TEXT,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS home_financial_due ON home_financial_operations(available_at,id)
 WHERE status IN ('pending','retry','running');
CREATE INDEX IF NOT EXISTS home_financial_booking ON home_financial_operations(booking_id,kind);
CREATE TABLE IF NOT EXISTS home_stripe_events (
 id TEXT PRIMARY KEY, kind TEXT NOT NULL, object_id TEXT NOT NULL, livemode BOOLEAN NOT NULL,
 payment_id UUID REFERENCES home_payments(id), helper_id TEXT REFERENCES users(id),
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','running','processed','ignored','retry','review_required')),
 attempts INTEGER NOT NULL DEFAULT 0, available_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 lease_until TIMESTAMPTZ, lease_token UUID, last_error TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS home_stripe_events_due ON home_stripe_events(available_at,id)
 WHERE status IN ('pending','retry','running');
CREATE UNIQUE INDEX IF NOT EXISTS home_cook_stripe_account ON cook_profiles(stripe_account_id) WHERE stripe_account_id IS NOT NULL;
CREATE OR REPLACE FUNCTION home_financial_payload_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.payload IS DISTINCT FROM OLD.payload OR NEW.kind IS DISTINCT FROM OLD.kind
 OR NEW.dedupe_key IS DISTINCT FROM OLD.dedupe_key OR NEW.payment_id IS DISTINCT FROM OLD.payment_id
 OR NEW.actor_id IS DISTINCT FROM OLD.actor_id OR NEW.booking_id IS DISTINCT FROM OLD.booking_id THEN
  RAISE EXCEPTION 'Financial operation identity and payload are immutable';
 END IF;
 RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS home_financial_payload_guard ON home_financial_operations;
CREATE TRIGGER home_financial_payload_guard BEFORE UPDATE ON home_financial_operations
 FOR EACH ROW EXECUTE FUNCTION home_financial_payload_immutable();
COMMIT;
