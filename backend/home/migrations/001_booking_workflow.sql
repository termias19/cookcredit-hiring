-- HOME DATABASE ONLY. Deliberately outside Hiring's migration directory.
BEGIN;
DO $$ BEGIN
  IF current_database() !~ '^cookcredit_home_(dev|test|staging|prod)$'
     AND NOT (current_database() = 'cookcredit_test' AND current_schema() ~ '^home_test_[a-f0-9]+$') THEN
    RAISE EXCEPTION 'Home migration requires a dedicated Home database';
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS home_runtime_guard (
  product TEXT PRIMARY KEY CHECK (product = 'home-services')
);
INSERT INTO home_runtime_guard VALUES ('home-services') ON CONFLICT DO NOTHING;
ALTER TABLE bookings ALTER COLUMN cook_id DROP NOT NULL;

CREATE TABLE IF NOT EXISTS home_visits (
  booking_id UUID PRIMARY KEY REFERENCES bookings(id),
  service TEXT NOT NULL CHECK (service IN ('cooking','cleaning','both')),
  time_zone TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 0 CHECK (version >= 0),
  instructions JSONB NOT NULL,
  consent_version TEXT NOT NULL,
  consented_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  reviewed_at TIMESTAMPTZ,
  reviewed_by TEXT REFERENCES users(id),
  helper_accepted_at TIMESTAMPTZ,
  issue_open BOOLEAN NOT NULL DEFAULT false,
  CHECK ((reviewed_at IS NULL) = (reviewed_by IS NULL))
);
CREATE TABLE IF NOT EXISTS home_helper_permissions (
  user_id TEXT PRIMARY KEY REFERENCES users(id),
  enabled BOOLEAN NOT NULL,
  cooking BOOLEAN NOT NULL,
  cleaning BOOLEAN NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS home_events (
  id UUID PRIMARY KEY,
  booking_id UUID REFERENCES bookings(id),
  actor_id TEXT NOT NULL REFERENCES users(id),
  action TEXT NOT NULL,
  version INTEGER,
  details JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK ((booking_id IS NULL) = (version IS NULL))
);
CREATE INDEX IF NOT EXISTS home_events_booking_time ON home_events(booking_id, created_at, id);
CREATE UNIQUE INDEX IF NOT EXISTS home_events_booking_version ON home_events(booking_id, version) WHERE booking_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS home_events_time ON home_events(created_at, id);
CREATE TABLE IF NOT EXISTS home_commands (
  actor_id TEXT NOT NULL REFERENCES users(id),
  key_hash TEXT NOT NULL,
  request_hash TEXT NOT NULL,
  result JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (actor_id, key_hash)
);
CREATE INDEX IF NOT EXISTS home_bookings_customer_page ON bookings(eater_id, created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS home_bookings_helper_page ON bookings(cook_id, created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS home_bookings_queue_page ON bookings(created_at DESC, id DESC);
COMMIT;
