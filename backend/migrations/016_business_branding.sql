BEGIN;

ALTER TABLE orgs ADD COLUMN IF NOT EXISTS brand_logo_url TEXT;
ALTER TABLE orgs ADD COLUMN IF NOT EXISTS brand_color TEXT NOT NULL DEFAULT '#1F6F5C';
ALTER TABLE orgs ADD COLUMN IF NOT EXISTS embed_allowed_origins TEXT[] NOT NULL DEFAULT '{}';
ALTER TABLE orgs ADD COLUMN IF NOT EXISTS public_embed_key TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS uq_orgs_public_embed_key
  ON orgs (public_embed_key) WHERE public_embed_key IS NOT NULL;

COMMIT;
