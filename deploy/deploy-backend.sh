#!/usr/bin/env bash
# Build the backend container (Cloud Build, from backend/Dockerfile) and deploy it to
# Cloud Run with the Cloud SQL connection, env config, and Secret Manager secrets wired in.
set -euo pipefail
cd "$(dirname "$0")"; source ./config.sh

echo "==> deploying $SERVICE to Cloud Run ($REGION) from ../backend"
[ -n "${PUBLIC_API_URL:-}" ] || { echo "ERROR: set PUBLIC_API_URL to the canonical HTTPS API origin."; exit 1; }
[ -n "${STRIPE_TEAM_PRICE_ID:-}" ] || { echo "ERROR: set STRIPE_TEAM_PRICE_ID to the recurring Team price."; exit 1; }
[ -n "${STRIPE_INTEGRATION_PRICE_ID:-}" ] || { echo "ERROR: set STRIPE_INTEGRATION_PRICE_ID to the recurring Integration price."; exit 1; }
[ -n "${REDIS_URL:-}" ] || { echo "ERROR: REDIS_URL is required for multi-instance production rate limits."; exit 1; }
RELEASE_ID="${RELEASE_ID:-r$(date -u +%Y%m%d%H%M%S)}"
[[ "$RELEASE_ID" =~ ^[a-z][a-z0-9-]*[a-z0-9]$ ]] || { echo "ERROR: RELEASE_ID must be a lowercase revision suffix."; exit 1; }
REVISION="${SERVICE}-${RELEASE_ID}"
[ ${#REVISION} -le 55 ] || { echo "ERROR: shorten RELEASE_ID to leave room for the migration job name."; exit 1; }

# Build the env-var string; append REDIS_URL only when set (empty => in-memory limiter, see config.sh).
ENV_VARS="FLASK_ENV=production,CLOUD_SQL_CONNECTION=${CLOUD_SQL_CONNECTION},DB_USER=${DB_USER},DB_NAME=${DB_NAME},FIREBASE_STORAGE_BUCKET=${FIREBASE_STORAGE_BUCKET},FRONTEND_URL=${FRONTEND_URL},PUBLIC_API_URL=${PUBLIC_API_URL},ASSESSMENT_PUBLIC_URL=${ASSESSMENT_PUBLIC_URL},SCORING_URL=${SCORING_URL},SCORING_AUDIENCE=${SCORING_URL},ADMIN_EMAILS=${ADMIN_EMAILS},GUNICORN_WORKERS=${GUNICORN_WORKERS:-1},GUNICORN_THREADS=${GUNICORN_THREADS:-8},DB_POOL_SIZE=${DB_POOL_SIZE:-5},DB_MAX_OVERFLOW=${DB_MAX_OVERFLOW:-2},TASKS_QUEUE=${TASKS_QUEUE},TASKS_TARGET_URL=${PUBLIC_API_URL}/api/skills/recompute,TASKS_OIDC_SA=${TASKS_OIDC_SA},TASKS_OIDC_AUDIENCE=${PUBLIC_API_URL},BUSINESS_BILLING_ENABLED=1,PARTNER_INTEGRATIONS_ENABLED=1,BEAM_AGENT_ENABLED=1,COOKCREDIT_EXPECT_MULTI_INSTANCE=1,BEAM_AGENT_MODEL=${BEAM_AGENT_MODEL},STRIPE_TEAM_PRICE_ID=${STRIPE_TEAM_PRICE_ID},STRIPE_TEAM_PRICE_DISPLAY=${STRIPE_TEAM_PRICE_DISPLAY},STRIPE_INTEGRATION_PRICE_ID=${STRIPE_INTEGRATION_PRICE_ID},STRIPE_INTEGRATION_PRICE_DISPLAY=${STRIPE_INTEGRATION_PRICE_DISPLAY},INTEGRATION_MONTHLY_ASSESSMENT_LIMIT=${INTEGRATION_MONTHLY_ASSESSMENT_LIMIT},ENTERPRISE_MONTHLY_ASSESSMENT_LIMIT=${ENTERPRISE_MONTHLY_ASSESSMENT_LIMIT}"
[ -n "${REDIS_URL:-}" ] && ENV_VARS="${ENV_VARS},REDIS_URL=${REDIS_URL}"

gcloud run deploy "$SERVICE" \
  --source ../backend \
  --no-traffic --revision-suffix "$RELEASE_ID" --tag "$RELEASE_ID" \
  --region "$REGION" \
  --service-account "$SA_EMAIL" \
  --add-cloudsql-instances "$CLOUD_SQL_CONNECTION" \
  --allow-unauthenticated \
  --port 8080 \
  --memory 1Gi --cpu 1 \
  --min-instances 1 --max-instances ${MAX_INSTANCES:-4} --concurrency ${CONCURRENCY:-16} \
  --no-cpu-throttling \
  --timeout 300 \
  --set-env-vars "$ENV_VARS" \
  --set-secrets "DB_PASS=DB_PASS:latest,FIREBASE_SERVICE_ACCOUNT_JSON=FIREBASE_SERVICE_ACCOUNT_JSON:latest,STRIPE_SECRET_KEY=STRIPE_SECRET_KEY:latest,STRIPE_WEBHOOK_SECRET=STRIPE_WEBHOOK_SECRET:latest,SENDGRID_API_KEY=SENDGRID_API_KEY:latest,SECRET_KEY=SECRET_KEY:latest,INTERNAL_SECRET=INTERNAL_SECRET:latest,WEBHOOK_SECRET_ENCRYPTION_KEY=WEBHOOK_SECRET_ENCRYPTION_KEY:latest,PARTNER_API_KEY_PEPPER=PARTNER_API_KEY_PEPPER:latest,GEMINI_API_KEY=GEMINI_API_KEY:latest"

URL=$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')
echo ""
echo "✓ prepared revision: $REVISION (no production traffic assigned)"
echo "  current service: $URL"
echo "  migrate this exact revision: ./migrate.sh '$REVISION'"
echo "  use the '$RELEASE_ID' tagged URL for smoke tests before a separate traffic promotion."
echo "  NOTE: set FRONTEND_URL to your real hosting URL/custom domain and add the Cloud Run URL"
echo "        to the frontend's API base; redeploy to refresh CORS if you change it."
