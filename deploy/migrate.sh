#!/usr/bin/env bash
# Apply every ordered DB migration against Cloud SQL via a Cloud Run JOB that reuses the
# deployed backend image — so it connects through the same Cloud SQL socket + DB_PASS
# secret, no local Auth Proxy needed. Idempotent (the runner tracks applied files).
set -euo pipefail
cd "$(dirname "$0")"; source ./config.sh

REVISION="${1:-}"
[ -n "$REVISION" ] || { echo "ERROR: pass the exact revision printed by deploy-backend.sh: ./migrate.sh <revision>"; exit 1; }
REVISION_SERVICE=$(gcloud run revisions describe "$REVISION" --region "$REGION" --format='value(metadata.labels."serving.knative.dev/service")')
[ "$REVISION_SERVICE" = "$SERVICE" ] || { echo "ERROR: revision does not belong to $SERVICE."; exit 1; }
IMAGE=$(gcloud run revisions describe "$REVISION" --region "$REGION" --format='value(status.imageDigest)')
[[ "$IMAGE" == *@sha256:* ]] || { echo "ERROR: revision has no resolved container image digest."; exit 1; }
# A revision-specific job avoids one release overwriting another migration job.
JOB="${REVISION}-migrate"
[ ${#JOB} -le 63 ] || { echo "ERROR: use a shorter release ID for the migration job name."; exit 1; }

echo "==> migration job $JOB (image: $IMAGE)"
gcloud run jobs deploy "$JOB" \
  --image "$IMAGE" \
  --region "$REGION" \
  --service-account "$SA_EMAIL" \
  --set-cloudsql-instances "$CLOUD_SQL_CONNECTION" \
  --set-env-vars "CLOUD_SQL_CONNECTION=${CLOUD_SQL_CONNECTION},DB_USER=${DB_USER},DB_NAME=${DB_NAME}" \
  --set-secrets "DB_PASS=DB_PASS:latest" \
  --command python --args migrations/run_migrations.py \
  --tasks 1 --parallelism 1 --max-retries 0 --task-timeout 600

echo "==> executing migrations"
gcloud run jobs execute "$JOB" --region "$REGION" --wait
echo "✓ schema applied (re-run anytime; already-applied files are skipped)."
