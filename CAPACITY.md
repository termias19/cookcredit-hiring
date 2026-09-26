# Stage 5 capacity validation

Stage 4 integration work is implemented. Stage 5 (capacity validation) is active. Stage 6 production deployment is live, but mass-launch acceptance remains open. A live URL alone does not close capacity or account acceptance.

## Reusable integrated workload

The existing Stage 4 harness is now `backend/scripts/verify_integrated_capacity.py`, with a guarded `backend/cloudbuild.capacity.yaml`. It accepts only disposable loopback PostGIS and the dedicated private test bucket. Run from the backend directory with the explicit hiring project:

```powershell
gcloud builds submit --config cloudbuild.capacity.yaml --project cookcredit-scoring
```

The test bucket must already be private, uniform-access, and restricted to synthetic load data, with a one-day cleanup lifecycle. Existing Cloud Build ADC must have access. Do not grant broad new permissions to make a test pass. Containers share the Cloud Build network so existing ADC works; no credential files are copied. The eight-applicant smoke must pass before the 240-applicant workload starts.

The sustained workload schedules eight synthetic applicants every ten seconds for thirty batches. It uses the real application routes, PostGIS, CV upload/download, 4MiB synthetic recordings, private Cloud Storage import/download, saved landmark payloads, processing completion, employer reads, company-isolation rejection, idempotent completion and concurrent delivery outboxes. Exact synthetic object generations are cleaned afterward. No existing users or recordings are read or deleted.

Identity and assessment-source metadata are adapters. SMTP and webhook receivers are loopback services. Playback uses a loopback adapter downloading the actual private GCS generation; IAM URL signing is not benchmarked. Rate limits are disabled to isolate component capacity and are verified separately across processes. This test cannot certify Google SMTP, Firebase login, production Cloud SQL throughput, browser responsiveness, raw camera capture or genuine scoring accuracy.

## Production rollout gates

1. Agree expected peak applicants, signup volume and recurring budget. Do not increase the three-instance API cap by assumption.
2. Size a dedicated-core regional Cloud SQL instance from sustained database measurements. Maintain backups/PITR, reserve administrative connections, and plan for the restart required by settings changes.
3. For Redis high availability, create a separate Standard instance with AUTH, TLS and private access. Basic-to-Standard is not an in-place tier change. Coordinate the rate-limit counter transition; do not reset quotas across a rolling split between two stores. Retain the previous store during the rollback window.
4. Provision valid transactional mail access and a verified CookCredit sender using the existing SendGrid adapter. Store the credential in Secret Manager, not Git or chat. Verify quota, sender/domain authentication and bounce handling before changing `AUTH_EMAIL_PROVIDER`. Preserve templates and disabled tracking. Test an explicitly authorized recipient before sending applicant traffic.
5. Run production-sized sustained integrated tests and verify queue draining, database connections, request latency, throttling and dependency-failure recovery. Local SMTP acceptance does not demonstrate inbox delivery.
6. Complete a fresh real production applicant journey: employer link, signup/login and verification, CV, consent, assessment submission, employer playback/resume and review outcome. The agent must not supply a user's consent or employment decision.

Connection budget: maximum instances Ã— Gunicorn workers Ã— (pool size + overflow), plus jobs/migrations and operational reserve. Check the database's actual max_connections and memory before changing these values. Max instance concurrency does not equal tested throughput.

## Current operational boundaries

Production remains three capped API instances, db-g1-small zonal SQL and BASIC 1GiB Redis. Read-only inspection on 2026-09-26 found max_connections=50. One Gunicorn worker per instance with pool3+overflow2 gives a15-connection API budget; preserve headroom for jobs, reserved/admin connections and overlapping revisions during rollout. Shared limits, request/release tracing, queue-age/failure alerts, backups and rollback records are enabled. Google SMTP has provider quotas and a five-message dispatcher batch cap. No mass-capacity certificate is claimed.

Official references: [Cloud SQL production settings](https://docs.cloud.google.com/sql/docs/postgres/instance-settings), [Cloud SQL high availability](https://docs.cloud.google.com/sql/docs/postgres/high-availability), [Redis tiers and pricing](https://cloud.google.com/memorystore/docs/redis/pricing), [Google Workspace sending limits](https://knowledge.workspace.google.com/admin/gmail/gmail-sending-limits-in-google-workspace).

## Measured 2026-09-26 result

The 240-applicant workload passed in293.45seconds:4MiB per recording (960MiB total), four employer workspaces, eight concurrent applicant slots,2,843 metadata calls,240 locally delivered emails and967 distinct webhook events delivered to the loopback receiver. Final webhook backlog0; no repeated event-ID deliveries; cross-company playback denied; cleanup errors0. p95:application0.304s, import1.158s, CV0.185s, playback URL resolution0.059s. Playback timing here excludes the subsequent GCS download (whose bytes were separately verified). Peak resident memory449MiB and observed checked-out DB connections9 on the disposable build VM. See capacity/2026-09-26.json for scope and complete measurements.

The first build stopped before workload execution because Docker's default network could not access Cloud Build ADC. The corrected configuration uses the existing cloudbuild network; no credentials or IAM permissions were added. The eight-applicant smoke and sustained run then passed.
