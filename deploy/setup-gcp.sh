#!/usr/bin/env bash
# One-time GCP infrastructure: APIs, Cloud SQL instance + DB, runtime service account + IAM.
# Idempotent — safe to re-run. Secrets + the DB password are handled by push-secrets.sh.
set -euo pipefail
cd "$(dirname "$0")"; source ./config.sh

[ "$PROJECT_ID" = "YOUR_GCP_PROJECT_ID" ] && { echo "ERROR: set PROJECT_ID in deploy/config.sh first."; exit 1; }

echo "==> project: $PROJECT_ID  region: $REGION"
gcloud config set project "$PROJECT_ID" >/dev/null

echo "==> enabling APIs (run, sqladmin, secretmanager, cloudbuild, tasks, scheduler)"
gcloud services enable \
  run.googleapis.com sqladmin.googleapis.com secretmanager.googleapis.com \
  cloudbuild.googleapis.com artifactregistry.googleapis.com \
  cloudtasks.googleapis.com cloudscheduler.googleapis.com redis.googleapis.com vpcaccess.googleapis.com

echo "==> Cloud SQL instance: $SQL_INSTANCE ($SQL_TIER, POSTGRES_16, $REGION)"
# Security posture: the instance keeps its default PUBLIC IP but adds ZERO authorized
# networks, so it is NOT directly reachable from the internet — only via the IAM-
# authenticated Cloud SQL connector (Cloud Run's --add-cloudsql-instances, and the local
# Auth Proxy), which uses mTLS. Deletion protection is ON to prevent an accidental drop.
# To harden further to private-IP-only, add `--no-assign-ip --network=<vpc>` here plus a
# Serverless VPC Access connector on Cloud Run (more setup; ask and I'll wire it).
if gcloud sql instances describe "$SQL_INSTANCE" >/dev/null 2>&1; then
  echo "    exists, skipping create"
else
  gcloud sql instances create "$SQL_INSTANCE" \
    --database-version=POSTGRES_16 --edition="$SQL_EDITION" --tier="$SQL_TIER" --region="$REGION" \
    --storage-type=SSD --storage-size=10GB --availability-type=zonal \
    --deletion-protection
fi

echo "==> database: $DB_NAME"
gcloud sql databases create "$DB_NAME" --instance="$SQL_INSTANCE" 2>/dev/null \
  && echo "    created" || echo "    exists, skipping"

echo "==> runtime service account: $SA_EMAIL"
gcloud iam service-accounts create "$RUNTIME_SA" \
  --display-name="CookCredit API (Cloud Run)" 2>/dev/null \
  && echo "    created" || echo "    exists, skipping"

echo "==> granting IAM (cloudsql.client) to the runtime SA"
# Least privilege: only cloudsql.client at the project level. Secret access is granted
# PER-SECRET (not project-wide) by push-secrets.sh, so this SA can read only the specific
# secrets it needs — not every secret in the project. The SA has no other roles.
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${SA_EMAIL}" --role="roles/cloudsql.client" --condition=None >/dev/null

cat <<EOF

✓ infrastructure ready.

Next:
  1. cp deploy/secrets.env.example deploy/secrets.env   # then fill it in (gitignored)
  2. ./deploy/push-secrets.sh        # pushes secrets + syncs the Cloud SQL password
  3. ./deploy/deploy-backend.sh      # builds the container, deploys Cloud Run
  4. ./deploy/migrate.sh             # applies the complete migration directory
  5. ./deploy/configure-workers.sh   # durable queue + recovery/webhook schedules
  6. ./deploy/deploy-frontend.sh     # vite build + Firebase Hosting
EOF
