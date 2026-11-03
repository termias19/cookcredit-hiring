-- HOME DATABASE ONLY. Never discovered by Hiring's migration runner.
BEGIN;
DO $$ BEGIN
  IF current_database() !~ '^cookcredit_home_(dev|test|staging|prod)$'
     AND NOT (current_database() = 'cookcredit_test' AND current_schema() ~ '^home_test_[a-f0-9]+$') THEN
    RAISE EXCEPTION 'Home migration requires a dedicated Home database';
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS home_rate_cards (
  id UUID PRIMARY KEY,
  previous_id UUID REFERENCES home_rate_cards(id),
  settings JSONB NOT NULL,
  created_by TEXT NOT NULL REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS home_pricing_head (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  rate_card_id UUID REFERENCES home_rate_cards(id)
);
INSERT INTO home_pricing_head(id) VALUES (1) ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS home_quotes (
  id UUID PRIMARY KEY,
  booking_id UUID NOT NULL REFERENCES home_visits(booking_id),
  rate_card_id UUID NOT NULL REFERENCES home_rate_cards(id),
  helper_id TEXT NOT NULL REFERENCES users(id),
  issued_version INTEGER NOT NULL CHECK (issued_version > 0),
  snapshot JSONB NOT NULL,
  digest TEXT NOT NULL CHECK (digest ~ '^[a-f0-9]{64}$'),
  created_by TEXT NOT NULL REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL CHECK (expires_at > created_at),
  UNIQUE (booking_id, issued_version),
  UNIQUE (booking_id, id)
);
ALTER TABLE home_visits ADD COLUMN IF NOT EXISTS quote_id UUID;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='home_visit_current_quote_fk'
                 AND conrelid='home_visits'::regclass) THEN
    ALTER TABLE home_visits ADD CONSTRAINT home_visit_current_quote_fk
      FOREIGN KEY (booking_id, quote_id) REFERENCES home_quotes(booking_id, id);
  END IF;
END $$;
CREATE TABLE IF NOT EXISTS home_quote_helper_acceptances (
  quote_id UUID PRIMARY KEY REFERENCES home_quotes(id),
  helper_id TEXT NOT NULL REFERENCES users(id),
  digest TEXT NOT NULL CHECK (digest ~ '^[a-f0-9]{64}$'),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS home_quote_approvals (
  quote_id UUID PRIMARY KEY REFERENCES home_quote_helper_acceptances(quote_id),
  customer_id TEXT NOT NULL REFERENCES users(id),
  digest TEXT NOT NULL CHECK (digest ~ '^[a-f0-9]{64}$'),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS home_material_reconciliations (
  quote_id UUID PRIMARY KEY REFERENCES home_quote_approvals(quote_id),
  booking_id UUID NOT NULL REFERENCES home_visits(booking_id),
  reviewed_by TEXT NOT NULL REFERENCES users(id),
  snapshot JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT home_reconciliation_booking_quote_fk FOREIGN KEY (booking_id, quote_id) REFERENCES home_quotes(booking_id, id)
);
CREATE INDEX IF NOT EXISTS home_rate_cards_created ON home_rate_cards(created_at DESC, id DESC);
COMMIT;
