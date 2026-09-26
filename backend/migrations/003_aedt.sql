-- 003_aedt.sql — LL144/AEDT compliance: the audit log gains the hard-gate outcomes, plus the
-- candidate-notice and opt-out (human-review) tables. Run after 002_business.sql. Idempotent.

ALTER TABLE aedt_audit_log ADD COLUMN IF NOT EXISTS hard_gate_outcomes JSONB;
ALTER TABLE orgs ADD COLUMN IF NOT EXISTS plan TEXT DEFAULT 'trial';   -- trial | team | enterprise

CREATE TABLE IF NOT EXISTS candidate_notices (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  cook_id         TEXT REFERENCES users(id) ON DELETE CASCADE,
  role_posting_id UUID REFERENCES role_postings(id) ON DELETE SET NULL,
  qualifications  JSONB,                          -- what is assessed + data sources
  method          TEXT DEFAULT 'in_app',          -- in_app | email
  notified_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS opt_out_requests (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  cook_id         TEXT REFERENCES users(id) ON DELETE CASCADE,
  role_posting_id UUID REFERENCES role_postings(id) ON DELETE SET NULL,
  reason          TEXT,
  status          TEXT DEFAULT 'open',            -- open | resolved
  requested_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_aedt_audit_role     ON aedt_audit_log(role_posting_id, created_at);
CREATE INDEX IF NOT EXISTS idx_candidate_notice    ON candidate_notices(cook_id, role_posting_id);
CREATE INDEX IF NOT EXISTS idx_opt_out_cook        ON opt_out_requests(cook_id, status);
