-- 002_business.sql — B2B hiring workspace: orgs, memberships, role postings (scorecards),
-- candidate pipeline, shortlists, parsed resume key-points, and the AEDT audit log.
-- Maps 1:1 to models/business.py. Run after 001_initial.sql. Idempotent (IF NOT EXISTS).

CREATE TABLE IF NOT EXISTS orgs (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name          TEXT NOT NULL,
  city          TEXT,
  location      JSONB,                         -- {lat, lng}
  cuisine_focus TEXT[] DEFAULT '{}',
  created_by    TEXT REFERENCES users(id),
  created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS org_memberships (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id     UUID REFERENCES orgs(id) ON DELETE CASCADE,
  user_id    TEXT REFERENCES users(id) ON DELETE CASCADE,
  seat_role  TEXT DEFAULT 'admin',             -- admin | recruiter | hiring_manager | viewer
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (org_id, user_id)
);

CREATE TABLE IF NOT EXISTS role_postings (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id       UUID REFERENCES orgs(id) ON DELETE CASCADE,
  title        TEXT NOT NULL,
  status       TEXT DEFAULT 'open',            -- draft | open | closed
  requirements JSONB DEFAULT '{}',             -- {required[],preferred[],skillFloor,certsRequired[],cuisines[],loc,radiusM}
  created_by   TEXT REFERENCES users(id),
  created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pipeline_cards (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  role_posting_id UUID REFERENCES role_postings(id) ON DELETE CASCADE,
  cook_id         TEXT REFERENCES users(id) ON DELETE CASCADE,
  stage           TEXT DEFAULT 'invited',      -- invited|assessing|verified|shortlisted|contacted|hired
  match_snapshot  JSONB,
  starred         BOOLEAN DEFAULT FALSE,
  updated_at      TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (role_posting_id, cook_id)
);

CREATE TABLE IF NOT EXISTS shortlists (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id     UUID REFERENCES orgs(id) ON DELETE CASCADE,
  name       TEXT DEFAULT 'Shortlist',
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS shortlist_members (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  shortlist_id UUID REFERENCES shortlists(id) ON DELETE CASCADE,
  cook_id      TEXT REFERENCES users(id) ON DELETE CASCADE,
  added_at     TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (shortlist_id, cook_id)
);

CREATE TABLE IF NOT EXISTS resume_keypoints (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  cook_id          TEXT REFERENCES users(id) ON DELETE CASCADE,
  version          INTEGER DEFAULT 1,
  points           JSONB DEFAULT '[]',         -- [{canonical_id,label,category,evidence_span,confidence}]
  file_hash        TEXT,
  taxonomy_version TEXT,
  model_version    TEXT,
  parsed_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS aedt_audit_log (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  candidate_id    TEXT,
  role_posting_id UUID REFERENCES role_postings(id) ON DELETE SET NULL,
  requirement_set JSONB,
  feature_weights JSONB,
  match_total     NUMERIC(5,4),
  surface         TEXT,                         -- 'b2b' | 'eater'
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_org_memberships_user   ON org_memberships(user_id);
CREATE INDEX IF NOT EXISTS idx_role_postings_org      ON role_postings(org_id, status);
CREATE INDEX IF NOT EXISTS idx_pipeline_cards_role    ON pipeline_cards(role_posting_id);
CREATE INDEX IF NOT EXISTS idx_shortlist_members_list ON shortlist_members(shortlist_id);
CREATE INDEX IF NOT EXISTS idx_resume_keypoints_cook  ON resume_keypoints(cook_id, version);
