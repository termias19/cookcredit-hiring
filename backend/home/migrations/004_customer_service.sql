BEGIN;
DO $$ BEGIN
 IF current_database() !~ '^cookcredit_home_(dev|test|staging|prod)$'
 AND NOT (current_database()='cookcredit_test' AND current_schema() ~ '^home_test_[a-f0-9]+$') THEN
  RAISE EXCEPTION 'Home migration requires a dedicated Home database';
 END IF;
END $$;
ALTER TABLE home_visits ADD COLUMN IF NOT EXISTS service_minutes JSONB;
ALTER TABLE home_visits ADD COLUMN IF NOT EXISTS recipient JSONB;
ALTER TABLE home_financial_operations ADD COLUMN IF NOT EXISTS mutation_started_at TIMESTAMPTZ;
-- Conservative upgrade for an older worker's uncertain provider requests.
-- Never turn a pre-upgrade attempt into a brand-new external mutation.
UPDATE home_financial_operations SET mutation_started_at=first_started_at
 WHERE mutation_started_at IS NULL AND first_started_at IS NOT NULL AND kind<>'expire';
CREATE TABLE IF NOT EXISTS home_households (
 user_id TEXT PRIMARY KEY REFERENCES eater_profiles(user_id), instructions JSONB NOT NULL,
 consented_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS home_callbacks (
 id UUID PRIMARY KEY, fingerprint TEXT NOT NULL, name TEXT NOT NULL, phone TEXT NOT NULL,
 preferred_time TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'requested'
 CHECK(status IN ('requested','contacting','closed')), version INTEGER NOT NULL DEFAULT 0,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS home_callbacks_queue ON home_callbacks(created_at DESC,id DESC) WHERE status<>'closed';
CREATE TABLE IF NOT EXISTS home_receipts (
 id UUID PRIMARY KEY, booking_id UUID NOT NULL REFERENCES home_visits(booking_id),
 quote_id UUID NOT NULL REFERENCES home_quotes(id), uploaded_by TEXT NOT NULL REFERENCES users(id),
 request_hash TEXT UNIQUE NOT NULL, original_hash TEXT NOT NULL,
 object_path TEXT NOT NULL, generation TEXT, sha256 TEXT,
 status TEXT NOT NULL DEFAULT 'uploading' CHECK(status IN ('uploading','ready','failed')),
 size_bytes INTEGER NOT NULL DEFAULT 0 CHECK(size_bytes BETWEEN 0 AND 8388608),
 content_type TEXT NOT NULL CHECK(content_type IN ('image/jpeg','image/png')),
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 FOREIGN KEY(booking_id,quote_id) REFERENCES home_quotes(booking_id,id),
 CHECK(status<>'ready' OR (size_bytes>0 AND generation IS NOT NULL AND sha256 ~ '^[a-f0-9]{64}$'))
);
CREATE INDEX IF NOT EXISTS home_receipts_booking ON home_receipts(booking_id,created_at);
CREATE OR REPLACE FUNCTION home_receipt_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF OLD.status='ready' OR ROW(NEW.id,NEW.booking_id,NEW.quote_id,NEW.uploaded_by,NEW.request_hash,NEW.original_hash,NEW.object_path,NEW.created_at)
 IS DISTINCT FROM ROW(OLD.id,OLD.booking_id,OLD.quote_id,OLD.uploaded_by,OLD.request_hash,OLD.original_hash,OLD.object_path,OLD.created_at) THEN
  RAISE EXCEPTION 'Receipt identity and ready evidence are immutable';
 END IF;
 RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS home_receipt_immutable ON home_receipts;
CREATE TRIGGER home_receipt_immutable BEFORE UPDATE ON home_receipts FOR EACH ROW EXECUTE FUNCTION home_receipt_immutable();
CREATE TABLE IF NOT EXISTS home_notification_cursors (
 event_id UUID PRIMARY KEY REFERENCES home_events(id), status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','done')),
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS home_notifications_pending ON home_notification_cursors(created_at,event_id) WHERE status='pending';
CREATE INDEX IF NOT EXISTS home_mail_due ON account_emails(available_at,id) WHERE status IN ('pending','sending');
CREATE OR REPLACE FUNCTION home_event_notification_pointer() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 INSERT INTO home_notification_cursors(event_id) VALUES(NEW.id) ON CONFLICT DO NOTHING;
 RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS home_notification_pointer ON home_events;
CREATE TRIGGER home_notification_pointer AFTER INSERT ON home_events FOR EACH ROW EXECUTE FUNCTION home_event_notification_pointer();
INSERT INTO home_notification_cursors(event_id) SELECT id FROM home_events ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS home_access_audit (
 id UUID PRIMARY KEY, actor_id TEXT NOT NULL REFERENCES users(id), action TEXT NOT NULL,
 subject_id TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS home_access_audit_time ON home_access_audit(created_at DESC,id DESC);
CREATE UNIQUE INDEX IF NOT EXISTS home_account_welcome_once ON home_events(actor_id,action) WHERE action='home_account_created';
COMMIT;
