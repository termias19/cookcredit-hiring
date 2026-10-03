# CookCredit hiring

Employer workspaces, role applications, consented knife-skill recordings and human review. Hiring reuses the existing CookCredit assessment and original hand/knife overlay; it does not introduce another scorer.

- `backend/`: Flask API, PostgreSQL migrations, private storage and durable email/webhook outboxes.
- `frontend/`: React hiring workspace and same-origin assessment packaging.
- `public-site/`: public company, research, contact and hiring pages.
- `contact-service/`: existing website contact service.
- `deploy/`: targeted deployment/validation tools. Read their defaults before using them.

See [OPERATIONS.md](OPERATIONS.md) for release tracing, errors, retention, capacity limits and rollback. GitHub Actions runs backend/database tests, frontend tests and a secret scan. It does not automatically deploy production or access real applicant data.

Read [SECURITY.md](SECURITY.md) for company isolation, seat permissions, evidence
access, audit coverage and known gaps. [AUTH_FLOW.md](AUTH_FLOW.md) describes account
creation and verification. These documents distinguish implemented controls from
customer journeys that still require live acceptance.

## Local verification

Use Python3.12, Node22 and a disposable PostgreSQL/PostGIS16 database. Install `backend/requirements.txt` plus pytest8.3.5, and run `npm ci` in frontend. Run `node --test tests/*.test.mjs` there. For backend integration tests set HIRING_TEST_DATABASE_URL to a localhost database owned by the dedicated `cookcredit_test` user, then run `python -m pytest tests -q` from backend. Never point test variables at production.

The initial public history is a reviewed source snapshot. Earlier private development history and operational receipts remain local and were not published. Public Firebase web identifiers are intentionally shipped by browsers; exact scanner exceptions do not cover private credentials.
