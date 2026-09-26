-- CookCredit: Initial Schema Migration
-- PostgreSQL 16 + PostGIS
-- Run: psql $DATABASE_URL -f backend/migrations/001_initial.sql

BEGIN;

-- Enable PostGIS
CREATE EXTENSION IF NOT EXISTS postgis;

-- Enable uuid generation
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ══════════════════════════════════════════════════════════════════════════════
-- TABLES
-- ══════════════════════════════════════════════════════════════════════════════

-- Users (synced from Firebase Auth on first login)
CREATE TABLE users (
  id TEXT PRIMARY KEY,                -- Firebase UID
  email TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  phone TEXT,
  roles TEXT[] DEFAULT '{eater}',     -- ['eater'], ['cook'], ['eater','cook']
  active_role TEXT DEFAULT 'eater',
  photo_url TEXT,
  fcm_token TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Eater-specific: home address + location
CREATE TABLE eater_profiles (
  user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  address_street TEXT,
  address_city TEXT,
  address_state TEXT,
  address_zip TEXT,
  location GEOGRAPHY(POINT, 4326),
  dietary_preferences TEXT[],
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Cook-specific profile
CREATE TABLE cook_profiles (
  user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  bio TEXT,
  specialties TEXT[],
  cuisines TEXT[],
  price_per_hour NUMERIC(6,2),
  travel_radius_miles NUMERIC(4,1),
  base_location GEOGRAPHY(POINT, 4326),
  base_city TEXT,
  base_state TEXT,
  portfolio_photos TEXT[],
  stripe_account_id TEXT,
  stripe_onboarded BOOLEAN DEFAULT FALSE,
  skill_score NUMERIC(5,2),   -- 0..100.00 (4,2 overflowed on a perfect 100)
  skill_verified BOOLEAN DEFAULT FALSE,
  years_experience INTEGER,
  dietary_capabilities TEXT[],
  approved BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Dishes a cook can make
CREATE TABLE dishes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  cook_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  description TEXT,
  photo_url TEXT,
  sort_order INTEGER DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Cook availability (recurring weekly slots)
CREATE TABLE cook_availability (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  cook_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  day_of_week INTEGER NOT NULL CHECK (day_of_week BETWEEN 0 AND 6),
  start_hour INTEGER NOT NULL CHECK (start_hour BETWEEN 0 AND 23),
  end_hour INTEGER NOT NULL CHECK (end_hour BETWEEN 0 AND 23),
  UNIQUE(cook_id, day_of_week, start_hour)
);

-- Blocked dates (one-off unavailable)
CREATE TABLE cook_blocked_dates (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  cook_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  blocked_date DATE NOT NULL,
  reason TEXT,
  UNIQUE(cook_id, blocked_date)
);

-- Eater pantry
CREATE TABLE pantry_items (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  category TEXT,
  item_type TEXT DEFAULT 'staple',
  added_at TIMESTAMPTZ DEFAULT NOW()
);

-- Bookings
CREATE TABLE bookings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  eater_id TEXT NOT NULL REFERENCES users(id),
  cook_id TEXT NOT NULL REFERENCES users(id),
  status TEXT DEFAULT 'requested'
    CHECK (status IN ('requested','accepted','ingredient_request','confirmed',
                      'in_progress','pending_confirmation','completed','cancelled','disputed')),
  scheduled_date DATE NOT NULL,
  scheduled_start_time TIME NOT NULL,
  estimated_duration NUMERIC(3,1) NOT NULL,
  eater_address TEXT,
  eater_location GEOGRAPHY(POINT, 4326),
  price_per_hour NUMERIC(6,2) NOT NULL,
  estimated_total NUMERIC(8,2) NOT NULL,
  actual_duration NUMERIC(3,1),
  final_total NUMERIC(8,2),
  platform_fee NUMERIC(8,2),
  cook_payout NUMERIC(8,2),
  stripe_payment_intent_id TEXT,
  eater_notes TEXT,
  cook_notes TEXT,
  cancellation_reason TEXT,
  cancelled_by TEXT CHECK (cancelled_by IN ('eater','cook','system')),
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Ingredient requests (cook asks eater to pick up items)
CREATE TABLE ingredient_requests (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  booking_id UUID NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
  item TEXT NOT NULL,
  note TEXT
);

-- Reviews (bidirectional)
CREATE TABLE reviews (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  booking_id UUID NOT NULL REFERENCES bookings(id),
  reviewer_id TEXT NOT NULL REFERENCES users(id),
  reviewee_id TEXT NOT NULL REFERENCES users(id),
  role TEXT NOT NULL CHECK (role IN ('eater_reviewing_cook','cook_reviewing_eater')),
  rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
  text TEXT,
  tags TEXT[],
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(booking_id, reviewer_id)
);

-- Booking-scoped messages
CREATE TABLE messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  booking_id UUID NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
  sender_id TEXT NOT NULL REFERENCES users(id),
  text TEXT NOT NULL,
  read BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ══════════════════════════════════════════════════════════════════════════════
-- INDEXES
-- ══════════════════════════════════════════════════════════════════════════════

CREATE INDEX idx_cook_profiles_location ON cook_profiles USING GIST(base_location);
CREATE INDEX idx_eater_profiles_location ON eater_profiles USING GIST(location);
CREATE INDEX idx_bookings_cook ON bookings(cook_id, status);
CREATE INDEX idx_bookings_eater ON bookings(eater_id, status);
CREATE INDEX idx_bookings_date ON bookings(cook_id, scheduled_date);
CREATE INDEX idx_dishes_cook ON dishes(cook_id, sort_order);
CREATE INDEX idx_pantry_user ON pantry_items(user_id, item_type);
CREATE INDEX idx_reviews_reviewee ON reviews(reviewee_id, rating);
CREATE INDEX idx_cook_availability_cook ON cook_availability(cook_id, day_of_week);
CREATE INDEX idx_messages_booking ON messages(booking_id, created_at);

-- ══════════════════════════════════════════════════════════════════════════════
-- updated_at TRIGGER
-- ══════════════════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_users_updated_at BEFORE UPDATE ON users
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_eater_profiles_updated_at BEFORE UPDATE ON eater_profiles
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_cook_profiles_updated_at BEFORE UPDATE ON cook_profiles
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_bookings_updated_at BEFORE UPDATE ON bookings
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

COMMIT;
