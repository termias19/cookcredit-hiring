-- Reuse the bounded account-mail outbox. Tokens are encrypted until delivery.
ALTER TABLE account_emails ADD COLUMN IF NOT EXISTS invitation_id UUID;
ALTER TABLE account_emails ADD COLUMN IF NOT EXISTS invitation_token_ciphertext TEXT;
ALTER TABLE account_emails DROP CONSTRAINT IF EXISTS account_emails_kind_check;
ALTER TABLE account_emails ADD CONSTRAINT account_emails_kind_check
 CHECK (kind IN ('verify','welcome','reset','access_requested','access_approved','workspace_invite'));
