BEGIN;

CREATE TABLE IF NOT EXISTS org_assessment_usage (
  id UUID PRIMARY KEY,
  org_id UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  period_start DATE NOT NULL,
  environment TEXT NOT NULL DEFAULT 'live' CHECK (environment IN ('test','live')),
  request_count INTEGER NOT NULL DEFAULT 0 CHECK (request_count >= 0),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_org_assessment_usage_period UNIQUE (org_id, period_start, environment)
);

CREATE INDEX IF NOT EXISTS idx_org_assessment_usage_org_period
  ON org_assessment_usage (org_id, environment, period_start DESC);

COMMIT;
