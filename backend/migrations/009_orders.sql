-- 009_orders.sql — the settlement record for an eater choosing a cook's beam response.
--
-- The beam flow itself stays PAYMENT-AGNOSTIC (008_beams.sql): choosing a cook only connects
-- the two parties. This table is where a payment method attaches to that pick. ET pays via
-- Chapa (telebirr / Chapa / CBE Birr all settle through Chapa) or cash-on-delivery; the same
-- row also serves the US (Stripe) path. One order per chosen beam response.
--
-- Idempotent DDL (IF NOT EXISTS); the runner applies it on an AUTOCOMMIT connection and this
-- file owns its own transaction. Reuses update_updated_at() from 001_initial.sql.

BEGIN;

CREATE TABLE IF NOT EXISTS orders (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  beam_id          UUID NOT NULL REFERENCES beams(id) ON DELETE CASCADE,
  beam_response_id UUID NOT NULL REFERENCES beam_responses(id) ON DELETE CASCADE,
  eater_id         TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  cook_id          TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  amount           NUMERIC(8,2),                          -- snapshot of the cook's quote; may be null
  currency         TEXT NOT NULL DEFAULT 'USD',           -- set per market at insert ('ETB' for ET)
  payment_method   TEXT NOT NULL
                     CHECK (payment_method IN ('cod','chapa','telebirr','cbe')),
  payment_status   TEXT NOT NULL DEFAULT 'pending'
                     CHECK (payment_status IN ('pending','awaiting_payment','paid','cod_pending','failed','cancelled','refunded')),
  chapa_tx_ref     TEXT,                                  -- Chapa transaction reference (online ET)
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_orders_beam_response UNIQUE (beam_response_id)  -- one order per chosen response
);

CREATE INDEX IF NOT EXISTS idx_orders_eater ON orders (eater_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_orders_cook  ON orders (cook_id, payment_status, created_at DESC);
-- Idempotency for the Chapa verify/callback: a tx_ref maps to at most one order.
CREATE UNIQUE INDEX IF NOT EXISTS uq_orders_chapa_tx_ref ON orders (chapa_tx_ref) WHERE chapa_tx_ref IS NOT NULL;

DROP TRIGGER IF EXISTS trg_orders_updated_at ON orders;
CREATE TRIGGER trg_orders_updated_at BEFORE UPDATE ON orders
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

COMMIT;
