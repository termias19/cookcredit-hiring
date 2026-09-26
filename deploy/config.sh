# Shared deploy config — sourced by the other deploy/*.sh scripts.
# EDIT PROJECT_ID (required). Everything else has a sane default; override via env if needed.
# This file is safe to commit (no secrets). Real secret VALUES go in deploy/secrets.env (gitignored).
#
# NOTE (Windows/Git-Bash): do NOT pass a leading-slash value like DB_SOCKET_DIR=/cloudsql to
# gcloud here — MSYS rewrites it to C:/Program Files/Git/cloudsql. The backend code already
# defaults DB_SOCKET_DIR to /cloudsql inside the container, so it is intentionally NOT set below.

export PROJECT_ID="${PROJECT_ID:-cookcredit-scoring}"          # backend + Cloud SQL + secrets (same project as the GPU scorer)
export REGION="${REGION:-us-central1}"                          # match the GPU scorer's region (co-located)

# Pin every gcloud call in these scripts to PROJECT_ID, regardless of the developer's
# active `gcloud config` project. Without this, a deploy once targeted whatever project
# happened to be active (a DIFFERENT product's prod) and failed only thanks to IAM.
export CLOUDSDK_CORE_PROJECT="$PROJECT_ID"

# Cloud SQL (Postgres + PostGIS)
export SQL_INSTANCE="${SQL_INSTANCE:-cookcredit-db}"
export SQL_EDITION="${SQL_EDITION:-ENTERPRISE}"   # ENTERPRISE supports cheap shared-core tiers; the
                                                  # project defaults to ENTERPRISE_PLUS which rejects them.
export SQL_TIER="${SQL_TIER:-db-g1-small}"   # ~50 conns. db-f1-micro is cheaper (~25 conns) but
                                             # then drop GUNICORN_WORKERS to 1 (see connection budget in README).
export DB_NAME="${DB_NAME:-cookcredit}"
export DB_USER="${DB_USER:-postgres}"
export CLOUD_SQL_CONNECTION="${PROJECT_ID}:${REGION}:${SQL_INSTANCE}"

# Cloud Run backend
export SERVICE="${SERVICE:-cookcredit-api}"
export RUNTIME_SA="${RUNTIME_SA:-cookcredit-api}"   # service-account id (the part before @)

# Firebase (Auth + Storage + Hosting) — these are GCP-native, hence one cloud.
export FIREBASE_PROJECT="${FIREBASE_PROJECT:-foodnlit-1123e}"
export FIREBASE_STORAGE_BUCKET="${FIREBASE_STORAGE_BUCKET:-foodnlit-1123e.firebasestorage.app}"

# The frontend URL the backend allows for CORS + Stripe redirects. Defaults to the
# Firebase Hosting URL; set a custom domain (e.g. https://cookcredit.com) once mapped.
export FRONTEND_URL="${FRONTEND_URL:-https://${FIREBASE_PROJECT}.web.app}"
export PUBLIC_API_URL="${PUBLIC_API_URL:-}"
export ASSESSMENT_PUBLIC_URL="${ASSESSMENT_PUBLIC_URL:-https://cookcredit-knife-demo.web.app/}"

# GPU scoring service (same project) + the dual-score recompute env the backend reads.
# SCORING_URL is the live L4 scorer; the backend mints an ID token (audience=SCORING_URL)
# from its runtime SA, which is granted run.invoker on the scorer (same project = in-domain).
export SCORING_URL="${SCORING_URL:-https://cookcredit-scoring-eqqoi6wp6a-uc.a.run.app}"
export ADMIN_EMAILS="${ADMIN_EMAILS:-eassefa@cookcredit.com}"   # cook-application reviewers
export BEAM_AGENT_MODEL="${BEAM_AGENT_MODEL:-gemini-2.5-flash}"
export STRIPE_TEAM_PRICE_ID="${STRIPE_TEAM_PRICE_ID:-}"
export STRIPE_TEAM_PRICE_DISPLAY="${STRIPE_TEAM_PRICE_DISPLAY:-\$99/month}"
export STRIPE_INTEGRATION_PRICE_ID="${STRIPE_INTEGRATION_PRICE_ID:-}"
export STRIPE_INTEGRATION_PRICE_DISPLAY="${STRIPE_INTEGRATION_PRICE_DISPLAY:-\$299/month}"
export INTEGRATION_MONTHLY_ASSESSMENT_LIMIT="${INTEGRATION_MONTHLY_ASSESSMENT_LIMIT:-1000}"
export ENTERPRISE_MONTHLY_ASSESSMENT_LIMIT="${ENTERPRISE_MONTHLY_ASSESSMENT_LIMIT:-100000}"

# Durable background work. Cloud Scheduler calls the two dispatch endpoints; Cloud Tasks
# delivers one scoring job at a time to the recompute endpoint.
export TASKS_QUEUE="${TASKS_QUEUE:-projects/${PROJECT_ID}/locations/${REGION}/queues/cookcredit-scoring}"
export TASKS_OIDC_SA="${TASKS_OIDC_SA:-${SA_EMAIL:-${RUNTIME_SA}@${PROJECT_ID}.iam.gserviceaccount.com}}"

# Rate-limit storage (extensions.py). Production deployment refuses multi-instance startup without
# shared Redis, because memory counters reset independently on each worker and cold start.
# To provision (standing cost + a Serverless VPC connector is required for Cloud Run -> Memorystore):
#   gcloud redis instances create cookcredit-rl --region="$REGION" --size=1 --tier=basic
#   gcloud compute networks vpc-access connectors create cc-conn --region="$REGION" --range=10.8.0.0/28
#   # then add `--vpc-connector cc-conn` to deploy-backend.sh and set REDIS_URL=redis://<HOST>:6379 below
export REDIS_URL="${REDIS_URL:-}"

# Secret Manager secret names (values pushed by push-secrets.sh from deploy/secrets.env).
export SECRET_NAMES=(DB_PASS FIREBASE_SERVICE_ACCOUNT_JSON STRIPE_SECRET_KEY STRIPE_WEBHOOK_SECRET SENDGRID_API_KEY SECRET_KEY INTERNAL_SECRET WEBHOOK_SECRET_ENCRYPTION_KEY PARTNER_API_KEY_PEPPER GEMINI_API_KEY)

export SA_EMAIL="${RUNTIME_SA}@${PROJECT_ID}.iam.gserviceaccount.com"
