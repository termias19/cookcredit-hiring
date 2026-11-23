-- HOME DATABASE ONLY. Index existing bookings; no second calendar or data copy.
BEGIN;
DO $$ BEGIN
  IF current_database() !~ '^cookcredit_home_(dev|test|staging|prod)$'
     AND NOT (current_database() = 'cookcredit_test' AND current_schema() ~ '^home_test_[a-f0-9]+$') THEN
    RAISE EXCEPTION 'Home migration requires a dedicated Home database';
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS home_bookings_helper_calendar
  ON bookings(cook_id, scheduled_date, scheduled_start_time)
  WHERE cook_id IS NOT NULL AND status NOT IN ('cancelled', 'completed');
COMMIT;
