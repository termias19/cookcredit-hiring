# Stage 5 capacity validation

Stage 5 is complete for the agreed existing-budget scope: bounded early traffic, shared limits, overload handling, failure recovery and a documented scale-up path. The owner chose to keep current infrastructure while there is no traction. This is not a large-traffic capacity certification. Stage 6 is deployed; a fresh real production applicant journey remains an acceptance check.

## Reusable integrated workload

The existing Stage 4 harness is now `backend/scripts/verify_integrated_capacity.py`, with a guarded `backend/cloudbuild.capacity.yaml`. It accepts only disposable loopback PostGIS and the dedicated private test bucket. Run from the backend directory with the explicit hiring project:

```powershell
gcloud builds submit --config cloudbuild.capacity.yaml --project cookcredit-scoring
```

The test bucket must already be private, uniform-access, and restricted to synthetic load data, with a one-day cleanup lifecycle. Existing Cloud Build ADC must have access. Do not grant broad new permissions to make a test pass. Containers share the Cloud Build network so existing ADC works; no credential files are copied. The eight-applicant smoke must pass before the 240-applicant workload starts.

The sustained workload schedules eight synthetic applicants every ten seconds for thirty batches. It uses the real application routes, PostGIS, CV upload/download, 4MiB synthetic recordings, private Cloud Storage import/download, saved landmark payloads, processing completion, employer reads, company-isolation rejection, idempotent completion and concurrent delivery outboxes. Exact synthetic object generations are cleaned afterward. No existing users or recordings are read or deleted.

Identity and assessment-source metadata are adapters. SMTP and webhook receivers are loopback services. Playback uses a loopback adapter downloading the actual private GCS generation; IAM URL signing is not benchmarked. Rate limits are disabled to isolate component capacity and are verified separately across processes. This test cannot certify Google SMTP, Firebase login, production Cloud SQL throughput, browser responsiveness, raw camera capture or genuine scoring accuracy.

## Future traffic expansion gates (not required purchases now)

1. Before a campaign or increasing the three-instance API cap, agree expected peak applicants, signup volume and recurring budget. No infrastructure upgrade or paid provider change is part of the current release.
2. Size a dedicated-core regional Cloud SQL instance from sustained database measurements. Maintain backups/PITR, reserve administrative connections, and plan for the restart required by settings changes.
3. For Redis high availability, create a separate Standard instance with AUTH, TLS and private access. Basic-to-Standard is not an in-place tier change. Coordinate the rate-limit counter transition; do not reset quotas across a rolling split between two stores. Retain the previous store during the rollback window.
4. If signup demand exceeds the current mail allowance, provision valid transactional mail access and a verified CookCredit sender using the existing adapter. The owner-approval runtime validation currently requires Google SMTP: update and test that validation before switching providers. Store credentials in Secret Manager, not Git or chat. Verify quota, sender/domain authentication and bounce handling. Preserve templates and disabled tracking. Test an explicitly authorized recipient before sending applicant traffic.
5. Run production-sized sustained integrated tests and verify queue draining, database connections, request latency, throttling and dependency-failure recovery. Local SMTP acceptance does not demonstrate inbox delivery.
6. Complete a fresh real production applicant journey: employer link, signup/login and verification, CV, consent, assessment submission, employer playback/resume and review outcome. The agent must not supply a user's consent or employment decision.

Connection budget: maximum instances * Gunicorn workers * (pool size + overflow), plus jobs/migrations and operational reserve. Check the database's actual max_connections and memory before changing these values. Max instance concurrency does not equal tested throughput.

## Current operational boundaries

Production remains three capped API instances, db-g1-small zonal SQL and BASIC 1GiB Redis. Read-only inspection on 2026-09-26 found max_connections=50. One Gunicorn worker per instance with pool3+overflow2 gives a15-connection API budget; preserve headroom for jobs, reserved/admin connections and overlapping revisions during rollout. Shared limits, request/release tracing, queue-age/failure alerts, backups and rollback records are enabled. Google SMTP has provider quotas and a five-message dispatcher batch cap. No mass-capacity certificate is claimed.

Official references: [Cloud SQL production settings](https://docs.cloud.google.com/sql/docs/postgres/instance-settings), [Cloud SQL high availability](https://docs.cloud.google.com/sql/docs/postgres/high-availability), [Redis tiers and pricing](https://cloud.google.com/memorystore/docs/redis/pricing), [Google Workspace sending limits](https://knowledge.workspace.google.com/admin/gmail/gmail-sending-limits-in-google-workspace).

## Existing-budget safeguards and red team

Account and employer-access mail share a transactionally enforced 100-message pending/sending cap. Duplicate enqueue requests do not consume another slot. A full queue returns 503 with Retry-After: 60; SQL/Redis dependency failures return 503 with Retry-After: 5. Rate-limited responses provide Retry-After. Database connections have a five-second connect timeout, 30-second statement timeout, three-second lock timeout and 60-second idle-transaction timeout. Recording import remains outside database transactions.

The local full regression suite passed 577 tests (8 skipped). A real disposable Redis pause produced 503 and recovered to 200 on resume; concurrent PostgreSQL queue admissions could not exceed the cap; a real conflicting database lock timed out and the connection recovered after rollback. Shared Redis admitted 60 and rejected 20 of 80 requests across two processes and preserved counters in a new process. See [the red-team record](capacity/stage5-redteam-2026-09-26.md) for scope and limitations. No live saturation traffic or real applicant mail was generated.

## Measured 2026-09-26 result

The 240-applicant workload passed in293.45seconds:4MiB per recording (960MiB total), four employer workspaces, eight concurrent applicant slots,2,843 metadata calls,240 locally delivered emails and967 distinct webhook events delivered to the loopback receiver. Final webhook backlog0; no repeated event-ID deliveries; cross-company playback denied; cleanup errors0. p95:application0.304s, import1.158s, CV0.185s, playback URL resolution0.059s. Playback timing here excludes the subsequent GCS download (whose bytes were separately verified). Peak resident memory449MiB and observed checked-out DB connections9 on the disposable build VM. See capacity/2026-09-26.json for scope and complete measurements.

The first build stopped before workload execution because Docker's default network could not access Cloud Build ADC. The corrected configuration uses the existing cloudbuild network; no credentials or IAM permissions were added. The eight-applicant smoke and sustained run then passed.
