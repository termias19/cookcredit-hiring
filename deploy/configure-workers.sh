#!/usr/bin/env bash
# Create the durable scoring queue and OIDC-authenticated dispatch schedules.
set -euo pipefail
cd "$(dirname "$0")"; source ./config.sh

[ -n "${PUBLIC_API_URL:-}" ] || { echo "ERROR: set PUBLIC_API_URL first."; exit 1; }

gcloud tasks queues describe cookcredit-scoring --location "$REGION" >/dev/null 2>&1 || \
  gcloud tasks queues create cookcredit-scoring --location "$REGION" \
    --max-dispatches-per-second=10 --max-concurrent-dispatches=20 \
    --max-attempts=8 --min-backoff=10s --max-backoff=300s

upsert_schedule() {
  local name="$1" path="$2"
  if gcloud scheduler jobs describe "$name" --location "$REGION" >/dev/null 2>&1; then
    gcloud scheduler jobs update http "$name" --location "$REGION" \
      --schedule='* * * * *' --uri="${PUBLIC_API_URL}${path}" --http-method=POST \
      --oidc-service-account-email="$TASKS_OIDC_SA" --oidc-token-audience="$PUBLIC_API_URL"
  else
    gcloud scheduler jobs create http "$name" --location "$REGION" \
      --schedule='* * * * *' --uri="${PUBLIC_API_URL}${path}" --http-method=POST \
      --oidc-service-account-email="$TASKS_OIDC_SA" --oidc-token-audience="$PUBLIC_API_URL"
  fi
}

upsert_schedule cookcredit-scoring-dispatch /api/skills/dispatch-pending
upsert_schedule cookcredit-webhook-dispatch /api/partner/internal/dispatch-webhooks
upsert_schedule cookcredit-assessment-expiry /api/partner/internal/expire-assessment-requests

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${SA_EMAIL}" --role='roles/cloudtasks.enqueuer' --condition=None >/dev/null

# The API creates tasks that ask Google to mint an OIDC token for the same runtime
# identity. Cloud Tasks' service agent performs the minting at delivery time.
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
gcloud iam service-accounts add-iam-policy-binding "$TASKS_OIDC_SA" \
  --member="serviceAccount:${SA_EMAIL}" --role='roles/iam.serviceAccountUser' >/dev/null
gcloud iam service-accounts add-iam-policy-binding "$TASKS_OIDC_SA" \
  --member="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-cloudtasks.iam.gserviceaccount.com" \
  --role='roles/iam.serviceAccountTokenCreator' >/dev/null

echo "✓ durable queue and dispatch schedules configured"
