BEGIN;
DO $$ BEGIN
 IF current_database() !~ '^cookcredit_home_(dev|test|staging|prod)$'
 AND NOT (current_database()='cookcredit_test' AND current_schema() ~ '^home_test_[a-f0-9]+$') THEN
  RAISE EXCEPTION 'Home migration requires a dedicated Home database';
 END IF;
END $$;
-- Workflow metadata references the existing customer; no second contact/CRM.
CREATE TABLE IF NOT EXISTS home_customer_followups (
 user_id TEXT PRIMARY KEY REFERENCES users(id),
 status TEXT NOT NULL CHECK(status IN ('new','contacted','waiting','done')),
 contact_name TEXT CHECK(contact_name IS NULL OR length(contact_name) BETWEEN 1 AND 120),
 version INTEGER NOT NULL DEFAULT 0 CHECK(version>=0),
 activity_at TIMESTAMPTZ NOT NULL,
 updated_by TEXT NOT NULL REFERENCES users(id), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE home_callbacks ADD COLUMN IF NOT EXISTS owner_customer_id TEXT REFERENCES users(id);
CREATE INDEX IF NOT EXISTS home_callbacks_customer ON home_callbacks(owner_customer_id,created_at DESC,id DESC);
CREATE INDEX IF NOT EXISTS home_callbacks_contact ON home_callbacks(
 phone,lower(regexp_replace(btrim(name),'[[:space:]]+',' ','g')),created_at DESC,id DESC);
CREATE INDEX IF NOT EXISTS home_interest_activity ON home_events(actor_id,created_at DESC,id DESC)
 WHERE action IN ('service_interest_saved','service_interest_removed');
COMMIT;
