#!/usr/bin/env bash
# Build the React app pointed at the deployed backend, then deploy to Firebase Hosting.
# The frontend reads VITE_API_URL at BUILD time (utils/http.js, AuthContext.jsx,
# pushNotifications.js — default localhost:5000), so we bake in the Cloud Run URL here.
set -euo pipefail
cd "$(dirname "$0")"; source ./config.sh
cd ../frontend

API_URL="${VITE_API_URL:-$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)' 2>/dev/null || true)}"
[ -z "$API_URL" ] && { echo "ERROR: no backend URL — deploy the backend first (./deploy-backend.sh) or export VITE_API_URL."; exit 1; }
echo "==> building frontend with VITE_API_URL=$API_URL"

# .env.production.local has the highest Vite precedence and is gitignored by Vite
# convention (*.local). Removed after the build regardless of outcome.
echo "VITE_API_URL=$API_URL" > .env.production.local
trap 'rm -f .env.production.local' EXIT

# Use `npm install` (not `npm ci`): on Windows/Git-Bash, npm ci's clean pre-removal of
# node_modules/.bin fails with ERR_FS_EISDIR, and so does `rm -rf node_modules`. `npm install`
# reconciles in place from package-lock without that destructive step. (CI on Linux can use npm ci.)
npm install --no-audit --no-fund
rm -rf dist        # never publish a stale tree (e.g. a committed bundle baked against localhost)
npm run build      # -> frontend/dist  (what firebase.json hosting serves)

echo "==> deploying to Firebase Hosting (project $FIREBASE_PROJECT)"
npx firebase-tools deploy --only hosting --project "$FIREBASE_PROJECT"

cat <<EOF

✓ frontend live.
  Make sure the backend's FRONTEND_URL ($FRONTEND_URL) matches the hosting origin so
  CORS allows it. If you mapped a custom domain (cookcredit.com), set FRONTEND_URL to it
  in deploy/config.sh and re-run ./deploy-backend.sh.
EOF
