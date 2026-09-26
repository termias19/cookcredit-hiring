# CookCredit hiring operations

## Release identity

Deploy an immutable image built from a reviewed Git commit. Set RELEASE_COMMIT to that full commit in the API revision. Each response includes X-Request-ID and X-Release-Commit; server error JSON also includes requestId. Store the image digest, frontend Hosting version, Git commit and previous versions in each GitHub release. Production secrets belong in Secret Manager, never in this repository or release artifacts. A release is not accepted until CI and staging checks pass.

## Where failures appear

Google Cloud project: cookcredit-scoring. Production Cloud Run service: cookcredit-hiring. Shared Firebase identity and original learning assessment: foodnlit-1123e. Do not use another CLI default project.

Cloud Logging filters:

```
resource.type="cloud_run_revision"
resource.labels.service_name="cookcredit-hiring"
jsonPayload.event="request_failed"
```

Search jsonPayload.requestId for the ID shown by a failed request. The unhandled_exception event includes the exception class and file/function/line frames, without error messages, tokens, submitted answers or SQL values. Open those lines at jsonPayload.commit on GitHub; inspect the corresponding Cloud Run revision.

```
resource.type="cloud_run_revision"
resource.labels.service_name="cookcredit-hiring"
jsonPayload.event="queue_health"
severity>=ERROR
```

Queue events contain only queue name, counts, oldest age and release identity. Terminal failures or pending messages older than ten minutes remain visible even after dispatch batches become empty. Monitoring alerts route to the existing owner notification channel. Scheduler HTTP200 alone is not proof that an email or webhook was delivered.

Do not blindly resend terminal messages: confirm recipient/destination, why retries failed, deduplication state and whether a provider accepted the prior send. Keep event IDs and signed webhook payloads stable. Webhooks are at-least-once delivery; receivers must deduplicate event IDs.

## Capacity and rate limits

Shared Redis enforces application and per-company partner limits across processes. Do not substitute in-memory counters in production or disable limiting to hide load failures. Production readiness checks SQL and shared limits. Use isolated database/load probes for saturation tests; production load targets are refused by the supplied probe.

Database connection budget is instances * gunicorn workers * (DB_POOL_SIZE + DB_MAX_OVERFLOW), plus jobs/migrations and an administration reserve. Keep this below the database's measured max_connections with headroom, and retain a Cloud Run max-instance cap. Concurrency is a queueing setting, not proof of throughput. Increase database/Redis availability and capacity before increasing the cap beyond their verified envelope.

Google Workspace SMTP has account/provider sending quotas independent of API autoscaling. The bounded dispatcher and queue alerts prevent silent failure but do not increase that quota. Before a mass signup campaign, provision/verify an appropriate transactional delivery allowance or provider, test delivery and bounce handling, and publish the tested signup envelope. Never promise unlimited concurrency or mail delivery based on local tests.

## Retention and access

Private hiring recording, landmark and CV prefixes expire after 30 days. Active company logos are excluded from that lifecycle. CV links report expiration/unavailability instead of endless retries. Existing sharing checks and five-minute signed playback links still apply. Firebase disabled/revoked sessions are checked on verification with a maximum 30-second cache; company approval and application consent are checked separately.

## Rollback

Record current backend revision and Hosting versions before promotion. Shift traffic to the prior tested backend revision and release the prior finalized Hosting version when schema compatibility permits. Never restore a database automatically as part of a code rollback. Pause only the affected hiring jobs if necessary. Preserve recordings, learning, unrelated services and the owner's access. A first deployment has no previous production revision; contain traffic and restore public links using its private baseline record.

## Intentional product boundaries

Employer access requires owner approval. Approved trial workspaces can open five roles. Payments, automatic hiring decisions and automatic mailbox imports remain disabled. Applicants follow a role invitation without employer approval. Preview/sample banners must remain on deliberate development fixtures; production builds set VITE_PREVIEW=0 and VITE_DEPLOYMENT_ENVIRONMENT=production.
