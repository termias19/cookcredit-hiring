-- Administrative events complement existing applicant and evidence event records.
-- Append-only through the application: no update/delete API is provided.
CREATE TABLE IF NOT EXISTS workspace_activity (
  id UUID PRIMARY KEY,
  org_id UUID NOT NULL REFERENCES orgs(id),
  actor_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  target_id TEXT NOT NULL,
  detail JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_workspace_activity_page
  ON workspace_activity(org_id, created_at DESC, id DESC);
