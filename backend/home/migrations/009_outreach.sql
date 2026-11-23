BEGIN;
DO $$ BEGIN
 IF current_database() !~ '^cookcredit_home_(dev|test|staging|prod)$'
 AND NOT (current_database()='cookcredit_test' AND current_schema() ~ '^home_test_[a-f0-9]+$') THEN
  RAISE EXCEPTION 'Home migration requires a dedicated Home database';
 END IF;
END $$;
-- Owner drafts only. No recipient imports, subscriptions or mail jobs.
CREATE TABLE IF NOT EXISTS home_campaigns (
 id UUID PRIMARY KEY, subject TEXT NOT NULL, body TEXT NOT NULL,
 postal_address TEXT NOT NULL DEFAULT '',
 status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','trashed')),
 interval_days INTEGER NOT NULL DEFAULT 0 CHECK(interval_days IN (0,7,30)),
 next_run_at TIMESTAMPTZ, run_at TIMESTAMPTZ, cursor TEXT,
 revision INTEGER NOT NULL DEFAULT 1 CHECK(revision>0),
 design JSONB NOT NULL DEFAULT '{}'::jsonb CHECK(jsonb_typeof(design)='object'),
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMIT;
