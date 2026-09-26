BEGIN;

CREATE INDEX IF NOT EXISTS idx_hiring_applications_role_status_cursor
  ON hiring_applications (role_posting_id, status, submitted_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_hiring_applications_role_city_cursor
  ON hiring_applications (role_posting_id, lower(location->>'city'), submitted_at DESC, id DESC);

COMMIT;
