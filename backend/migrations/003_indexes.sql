-- 003_indexes.sql
-- Performance + integrity, no functional change.
--   * indexes the core "browse cooks" query needs (geo index already exists in 001)
--   * indexes missing FK / pagination / idempotency columns
--   * adds ON DELETE CASCADE to the user/booking FKs that lacked it (001 only
--     cascaded some), so deleting a user/booking can't orphan rows
-- Idempotent (safe to re-run). Apply:
--   psql "$DATABASE_URL" -f migrations/003_indexes.sql
-- Note: tables are small pre-launch so plain CREATE INDEX is fine inside a txn.
-- On a large LIVE table, run the CREATE INDEX lines with CONCURRENTLY *outside*
-- a transaction instead (cannot be inside BEGIN/COMMIT).

BEGIN;

-- ── array filters for browse (cuisine / specialty / dietary) -> GIN ──────────
CREATE INDEX IF NOT EXISTS idx_cook_cuisines    ON cook_profiles USING GIN (cuisines);
CREATE INDEX IF NOT EXISTS idx_cook_specialties ON cook_profiles USING GIN (specialties);
CREATE INDEX IF NOT EXISTS idx_cook_dietary     ON cook_profiles USING GIN (dietary_capabilities);
CREATE INDEX IF NOT EXISTS idx_eater_dietary    ON eater_profiles USING GIN (dietary_preferences);

-- ── browse hot path: only approved + skill-verified cooks are listed ─────────
CREATE INDEX IF NOT EXISTS idx_cook_browse ON cook_profiles (approved, skill_verified)
  WHERE approved AND skill_verified;

-- ── lookups used by the stripe/onboarding routes ─────────────────────────────
CREATE INDEX IF NOT EXISTS idx_cook_stripe_acct ON cook_profiles (stripe_account_id)
  WHERE stripe_account_id IS NOT NULL;

-- ── missing FK indexes (join perf) ───────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_messages_sender  ON messages (sender_id);
CREATE INDEX IF NOT EXISTS idx_reviews_reviewer ON reviews (reviewer_id);
CREATE INDEX IF NOT EXISTS idx_reviews_booking  ON reviews (booking_id);

-- ── pagination + Stripe webhook idempotency ──────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_bookings_created ON bookings (created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_bookings_payment_intent
  ON bookings (stripe_payment_intent_id) WHERE stripe_payment_intent_id IS NOT NULL;

-- ── add ON DELETE CASCADE where 001 left FKs un-cascaded ─────────────────────
-- (inline single-column FKs get the default name <table>_<column>_fkey)
ALTER TABLE bookings DROP CONSTRAINT IF EXISTS bookings_eater_id_fkey;
ALTER TABLE bookings ADD  CONSTRAINT bookings_eater_id_fkey
  FOREIGN KEY (eater_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE bookings DROP CONSTRAINT IF EXISTS bookings_cook_id_fkey;
ALTER TABLE bookings ADD  CONSTRAINT bookings_cook_id_fkey
  FOREIGN KEY (cook_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE reviews DROP CONSTRAINT IF EXISTS reviews_booking_id_fkey;
ALTER TABLE reviews ADD  CONSTRAINT reviews_booking_id_fkey
  FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE CASCADE;

ALTER TABLE reviews DROP CONSTRAINT IF EXISTS reviews_reviewer_id_fkey;
ALTER TABLE reviews ADD  CONSTRAINT reviews_reviewer_id_fkey
  FOREIGN KEY (reviewer_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE reviews DROP CONSTRAINT IF EXISTS reviews_reviewee_id_fkey;
ALTER TABLE reviews ADD  CONSTRAINT reviews_reviewee_id_fkey
  FOREIGN KEY (reviewee_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE messages DROP CONSTRAINT IF EXISTS messages_sender_id_fkey;
ALTER TABLE messages ADD  CONSTRAINT messages_sender_id_fkey
  FOREIGN KEY (sender_id) REFERENCES users(id) ON DELETE CASCADE;

COMMIT;
