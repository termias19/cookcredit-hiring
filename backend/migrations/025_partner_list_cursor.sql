-- Stable keyset pagination for large integration accounts. No offset scan.
CREATE INDEX IF NOT EXISTS idx_partner_invitations_cursor
    ON partner_invitations (org_id, environment, created_at DESC, id DESC);
