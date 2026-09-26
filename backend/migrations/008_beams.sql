-- 008_beams.sql — broadcast craving ("beam") + per-cook recipient/response rows.
--
-- One beam fans out to many cooks: a beam_responses recipient row is created per matched
-- cook. Each cook may respond (note + price); the eater reviews responders and picks ONE,
-- which marks the beam 'fulfilled'. PAYMENT-AGNOSTIC — no Stripe/price settlement happens
-- here, so it works identically in the US (Stripe) and ET/Addis (Chapa + cash) markets.
--
-- Idempotent DDL (IF NOT EXISTS); the runner applies it on an AUTOCOMMIT connection and this
-- file owns its own transaction. Reuses update_updated_at() from 001_initial.sql.

BEGIN;

CREATE TABLE IF NOT EXISTS beams (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  eater_id           TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  craving_text       TEXT NOT NULL,                       -- clamped <=500 in the route
  photo_url          TEXT,                                -- optional craving photo (cravings/{uid}/...)
  scope              TEXT NOT NULL DEFAULT 'citywide' CHECK (scope IN ('nearby','citywide')),
  city               TEXT,                                -- captured eater city; matched on lower(city)
  state              TEXT,
  eater_location     GEOGRAPHY(POINT, 4326),              -- nullable; ready for later ST_DWithin (no geocode yet)
  status             TEXT NOT NULL DEFAULT 'open'
                       CHECK (status IN ('open','fulfilled','expired','cancelled')),
  chosen_cook_id     TEXT REFERENCES users(id) ON DELETE SET NULL,
  chosen_response_id UUID,                                -- FK added below (circular ref)
  matched_count      INTEGER NOT NULL DEFAULT 0,          -- fan-out size at create (observability)
  expires_at         TIMESTAMPTZ NOT NULL DEFAULT (now() + interval '24 hours'),
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS beam_responses (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  beam_id      UUID NOT NULL REFERENCES beams(id) ON DELETE CASCADE,
  cook_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  status       TEXT NOT NULL DEFAULT 'pending'
                 CHECK (status IN ('pending','responded','declined','chosen','not_chosen')),
  note         TEXT,                                      -- clamped <=500
  price        NUMERIC(8,2),                              -- cook's quote (max 999999.99); never settled here
  seen_at      TIMESTAMPTZ,                               -- the "seen" concept (cook opened the beam)
  responded_at TIMESTAMPTZ,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_beam_responses_beam_cook UNIQUE (beam_id, cook_id)  -- one recipient row per cook
);

-- Circular FK added after both tables exist. ON DELETE SET NULL so deleting a response row
-- (cascade from a deleted beam never reaches here, but a manual delete) cannot orphan the beam.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'fk_beams_chosen_response'
  ) THEN
    ALTER TABLE beams ADD CONSTRAINT fk_beams_chosen_response
      FOREIGN KEY (chosen_response_id) REFERENCES beam_responses(id) ON DELETE SET NULL;
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_beams_city_open
  ON beams (lower(city), created_at DESC) WHERE status = 'open';        -- cook inbox (partial)
CREATE INDEX IF NOT EXISTS idx_beams_eater          ON beams (eater_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_beams_status_expires ON beams (status, expires_at);  -- lazy-expiry sweep
CREATE INDEX IF NOT EXISTS idx_beams_location       ON beams USING GIST (eater_location); -- later GPS radius
CREATE INDEX IF NOT EXISTS idx_beam_responses_cook  ON beam_responses (cook_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_beam_responses_beam  ON beam_responses (beam_id, status);

DROP TRIGGER IF EXISTS trg_beams_updated_at ON beams;
CREATE TRIGGER trg_beams_updated_at BEFORE UPDATE ON beams
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

COMMIT;
