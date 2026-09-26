# Stage 5: existing-budget validation and internal red team

Date: 2026-09-26. Scope: existing hiring infrastructure, no paid tier changes, no live flood, no real applicant mail or access decisions. This is an internal adversarial regression exercise, not an independent security audit or a promise of unlimited traffic.

## Findings fixed

- Dependency failures previously returned generic 500 responses without useful retry guidance. SQL/Redis failures now fail closed with 503, a request ID and Retry-After: 5. Logs retain safe exception type and endpoint rather than raw SQL or tokens.
- Mail dispatch batches were bounded, but admission could grow the durable backlog. Account and access mail now share a 100-message pending/sending cap protected by a PostgreSQL transaction advisory lock. Duplicate requests do not consume another slot. Saturation returns 503 with Retry-After: 60 and rolls back the transaction.
- Database queries and lock waits lacked explicit runtime bounds. Connection, statement, lock and idle-transaction timeouts now bound these failure modes. Slow recording import is outside the transaction and is not subject to the idle-transaction deadline.
- 429 responses now consistently supply Retry-After using the limiter reset time when available.

## Evidence

| Check | Result |
| --- | --- |
| Full backend and deployment regression suite against disposable PostGIS | 577 passed, 8 skipped; 104.84 seconds |
| New guard tests plus affected account/access/CV regressions | 69 passed |
| Concurrent mail admissions, real PostgreSQL | Nine callers at a test cap of three admitted exactly three; dedupe did not consume another slot; draining one allowed another |
| Real conflicting PostgreSQL advisory locks | Second connection hit SQLSTATE 55P03 within eight seconds; rollback restored usability |
| Real local Redis outage | Container pause caused HTTP 503 with Retry-After: 5; unpause restored HTTP 200 |
| Shared Redis across processes | 80 requests: 60 accepted, 20 limited; counters persisted in a fresh process; company keys isolated |
| Integrated capacity evidence reused | 240 synthetic applicants, 960 MiB recording transfers, queues drained, cleanup passed; see 2026-09-26.json |

The full suite includes adversarial authorization, company isolation, owner-only access, revoked consent, recording/CV binding, replay/idempotency, webhook signature and destination validation, and worker recovery. Eight environment-specific tests remained skipped; do not treat them as passing. The first full run found three test-order failures caused by the new test reusing the global limiter. The test now uses its own limiter; the affected subset and complete suite passed on rerun.

## Reproduce the new checks

Use an isolated loopback PostGIS database with test user cookcredit_test. Set DATABASE_URL and HIRING_TEST_DATABASE_URL to that database, apply migrations, then run from backend:

```text
python -m pytest tests/test_budget_overload.py tests/test_email_capacity.py tests/test_database_budget.py -q
python -m pytest tests ../deploy/tests -q
```

The outage check used only a disposable local Redis container and the actual application error handler. Never pause the managed production Redis service or run saturation tests against real users. Existing CI independently runs the full regression suite on Linux.

## Limits and next stage

Current caps remain three API instances, zonal db-g1-small SQL, BASIC Redis and Google SMTP. No high-availability or large-campaign throughput claim is made. The integrated test used synthetic identity, disposable SQL and loopback mail/webhook receivers; it does not prove inbox delivery or production-sized database capacity. Current spending still varies with usage within configured limits; a max-instance cap is not an absolute billing cap.

Stage 5 closes under the owner's existing-budget scope. Stage 6 acceptance includes a fresh real production employer-link-to-applicant-to-review journey, with the user's own consent. Future demand should trigger the measured expansion plan in CAPACITY.md, not speculative spending now.
