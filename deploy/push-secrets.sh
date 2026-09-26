#!/usr/bin/env bash
# Push secret VALUES from deploy/secrets.env into Secret Manager, grant the runtime SA
# per-secret access, and sync the Cloud SQL postgres password to DB_PASS. Idempotent
# (adds a new version each run). Re-run after rotating any key.
#
# Security:
#  - DB_PASS / SECRET_KEY / INTERNAL_SECRET are GENERATED strong when left blank or at the
#    example placeholder, so an empty or weak password can NEVER reach the internet-routable
#    DB superuser, and the deploy can't fail on a missing "reserved" secret.
#  - Secret values are written to Secret Manager via stdin/file (never the process argv).
set -euo pipefail
cd "$(dirname "$0")"; source ./config.sh

[ -f secrets.env ] || { echo "ERROR: create deploy/secrets.env from secrets.env.example first."; exit 1; }
# shellcheck disable=SC1091
set -a; source ./secrets.env; set +a

gen() { openssl rand -base64 36 | tr -d '\n/+=' | cut -c1-40; }   # strong, url-safe-ish

# DB_PASS must be strong and non-empty — it is the Postgres superuser password.
if [ -z "${DB_PASS:-}" ] || [ "${DB_PASS:-}" = "choose-a-strong-db-password" ]; then
  DB_PASS="$(gen)"; echo "  · DB_PASS was blank/placeholder — generated a strong one"
elif [ ${#DB_PASS} -lt 16 ]; then
  echo "ERROR: DB_PASS is shorter than 16 chars. Use a strong value, or leave it blank to auto-generate."; exit 1
fi
# Flask reserved secrets: generate if blank so the deploy never fails on a missing secret.
[ -z "${SECRET_KEY:-}" ]      && { SECRET_KEY="$(gen)";      echo "  · SECRET_KEY generated"; }
[ -z "${INTERNAL_SECRET:-}" ] && { INTERNAL_SECRET="$(gen)"; echo "  · INTERNAL_SECRET generated"; }
[ -z "${PARTNER_API_KEY_PEPPER:-}" ] && { PARTNER_API_KEY_PEPPER="$(gen)"; echo "  · PARTNER_API_KEY_PEPPER generated"; }
[ -z "${WEBHOOK_SECRET_ENCRYPTION_KEY:-}" ] && { WEBHOOK_SECRET_ENCRYPTION_KEY="$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"; echo "  · WEBHOOK_SECRET_ENCRYPTION_KEY generated"; }

CREATED=()
put_value() {  # name, value
  local name="$1" value="${2:-}"
  [ -z "$value" ] && { echo "  ! $name empty — skipping (set it in secrets.env)"; return; }
  gcloud secrets describe "$name" >/dev/null 2>&1 || gcloud secrets create "$name" --replication-policy=automatic >/dev/null
  printf '%s' "$value" | gcloud secrets versions add "$name" --data-file=- >/dev/null
  CREATED+=("$name"); echo "  ✓ $name"
}
put_file() {   # name, filepath
  local name="$1" path="${2:-}"
  { [ -z "$path" ] || [ ! -f "$path" ]; } && { echo "  ! $name file missing ($path) — skipping (set FIREBASE_SA_FILE)"; return; }
  gcloud secrets describe "$name" >/dev/null 2>&1 || gcloud secrets create "$name" --replication-policy=automatic >/dev/null
  gcloud secrets versions add "$name" --data-file="$path" >/dev/null
  CREATED+=("$name"); echo "  ✓ $name (from $path)"
}

echo "==> pushing secrets to Secret Manager"
put_value DB_PASS               "$DB_PASS"
put_value STRIPE_SECRET_KEY     "${STRIPE_SECRET_KEY:-}"
put_value STRIPE_WEBHOOK_SECRET "${STRIPE_WEBHOOK_SECRET:-}"
put_value SENDGRID_API_KEY      "${SENDGRID_API_KEY:-}"
put_value SECRET_KEY            "$SECRET_KEY"
put_value INTERNAL_SECRET       "$INTERNAL_SECRET"
put_value PARTNER_API_KEY_PEPPER "$PARTNER_API_KEY_PEPPER"
put_value WEBHOOK_SECRET_ENCRYPTION_KEY "$WEBHOOK_SECRET_ENCRYPTION_KEY"
put_value GEMINI_API_KEY        "${GEMINI_API_KEY:-}"
put_file  FIREBASE_SERVICE_ACCOUNT_JSON "${FIREBASE_SA_FILE:-}"

# Least privilege: grant secretAccessor only on the secrets that actually exist, and do
# NOT swallow failures — a missing grant would surface as a confusing cold-start failure.
echo "==> granting ${SA_EMAIL} secretAccessor on each created secret"
for s in "${CREATED[@]}"; do
  gcloud secrets add-iam-policy-binding "$s" \
    --member="serviceAccount:${SA_EMAIL}" --role="roles/secretmanager.secretAccessor" >/dev/null
  echo "  ✓ $s"
done

# Sync the live Cloud SQL password to DB_PASS. (This is the one spot the value is on the
# argv — acceptable since it runs only on the trusted operator machine; no `set -x` trace.)
echo "==> syncing Cloud SQL '${DB_USER}' password to DB_PASS"
gcloud sql users set-password "$DB_USER" --instance="$SQL_INSTANCE" --password="$DB_PASS" >/dev/null
echo "done."
