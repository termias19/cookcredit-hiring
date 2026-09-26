BEGIN;
CREATE TABLE IF NOT EXISTS hiring_applications (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  role_posting_id UUID NOT NULL REFERENCES role_postings(id) ON DELETE CASCADE,
  applicant_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'assessment_required'
    CHECK (status IN ('assessment_required','assessment_processing','ready','withdrawn')),
  question_schema JSONB NOT NULL DEFAULT '[]',
  answers JSONB NOT NULL DEFAULT '{}',
  location JSONB,
  attempt_limit INTEGER NOT NULL DEFAULT 3 CHECK (attempt_limit BETWEEN 1 AND 3),
  consent_version TEXT NOT NULL,
  consented_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  submitted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_hiring_application_role_applicant UNIQUE (role_posting_id, applicant_id)
);
CREATE TABLE IF NOT EXISTS hiring_assessment_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  application_id UUID NOT NULL REFERENCES hiring_applications(id) ON DELETE CASCADE,
  applicant_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  slot INTEGER NOT NULL CHECK (slot BETWEEN 1 AND 3),
  status TEXT NOT NULL DEFAULT 'started'
    CHECK (status IN ('started','processing','completed','expired')),
  engine_assessment_id TEXT,
  attempt_id UUID REFERENCES skill_attempts(id) ON DELETE SET NULL,
  started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  expires_at TIMESTAMPTZ NOT NULL,
  completed_at TIMESTAMPTZ,
  CONSTRAINT uq_hiring_assessment_slot UNIQUE (application_id, slot),
  CONSTRAINT uq_hiring_engine_assessment UNIQUE (engine_assessment_id)
);
CREATE TABLE IF NOT EXISTS hiring_application_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  application_id UUID NOT NULL REFERENCES hiring_applications(id) ON DELETE CASCADE,
  actor_id TEXT REFERENCES users(id) ON DELETE SET NULL,
  event_type TEXT NOT NULL,
  detail JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_hiring_applications_role_status
  ON hiring_applications(role_posting_id, status, submitted_at DESC);
CREATE INDEX IF NOT EXISTS idx_hiring_applications_applicant
  ON hiring_applications(applicant_id, submitted_at DESC);
CREATE INDEX IF NOT EXISTS idx_hiring_sessions_application
  ON hiring_assessment_sessions(application_id, slot);
CREATE INDEX IF NOT EXISTS idx_hiring_events_application
  ON hiring_application_events(application_id, created_at);
COMMIT;
