-- HOME DATABASE ONLY. Draft business rules; never seeds public availability.
BEGIN;
DO $$ BEGIN
 IF current_database() !~ '^cookcredit_home_(dev|test|staging|prod)$'
 AND NOT (current_database()='cookcredit_test' AND current_schema() ~ '^home_test_[a-f0-9]+$') THEN
  RAISE EXCEPTION 'Home migration requires a dedicated Home database';
 END IF;
END $$;
CREATE TABLE IF NOT EXISTS home_operating_rules (
 id INTEGER PRIMARY KEY CHECK(id=1), version INTEGER NOT NULL CHECK(version>0),
 settings JSONB NOT NULL CHECK(jsonb_typeof(settings)='object'),
 updated_by TEXT NOT NULL REFERENCES users(id), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMIT;
