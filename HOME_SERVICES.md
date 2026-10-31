# CookCredit Home service delivery

Home services let customers request cooking, cleaning or both. The backend
stores requests, consent, review, assignment, versioned quotes and approvals. It is
disabled by default and is not a public booking or payment service yet.

## Stages and acceptance gates

| Stage | Deliverable | Acceptance gate |
| --- | --- | --- |
| 1. Architecture and contract | Reuse Firebase identity and the existing User, CookProfile and Booking models in a separate Home runtime/database. Contract below. | Hiring never registers Home routes or runs Home migrations. |
| 2. Durable requests | Customer ownership, explicit visit consent, operator review, service-specific helper permissions, assignment, acceptance, cancellation, issue hold, audit and idempotency. Implemented in this branch. | PostgreSQL/API tests pass, including concurrent retries, stale writes, permission revocation and rollback. Provisioned runtime permissions still need staging acceptance. |
| 3. Quotes | Implemented: owner-controlled immutable rate cards, itemized capped offers, helper/customer approvals and manual receipt-review accounting. All money uses integer cents. | Tax requires explicit operator review. Actual receipt attachments and deployed SQL grants remain staging/interface gates. Preview figures are examples, not published rates. |
| 4. Payments and settlement | Implemented core: namespaced hosted checkout, signed durable inbox, canonical payment verification, leased financial operations, refunds, issue holds and transfer/reversal handling. | Deterministic provider/real SQL lifecycle passes. Actual live provider acceptance remains unpaid; checkout/refund/transfer/Connect have separate explicit gates. A return URL cannot mark paid. |
| 5. Connected interfaces | Implemented first pass in `frontend/home`: customer request/quote/receipts, helper work and Stripe account setup, owner pricing/review and private service desk. Separate Vite output; no Hiring PWA changes. | Browser task completion and staging acceptance remain open. Account creation reuses Firebase; self-submitted helper experience never grants access. |
| 6. Communications and accessibility | Implemented event pointers into the existing AccountEmail outbox/Google transport, private receipt photos, explicit household opt-in, family permission and no-account callback intake. Large controls and semantic forms. | Actual public-sender delivery, expired links and keyboard/screen-reader task completion remain open. No SMS provider exists; no SMS delivery is promised. Marketing is not enabled by service consent. |
| 7. Release | Separate staging deployment, security/retention review, bounded capacity test and production rollback plan. | Customer, helper and operator complete the real journey; payment acceptance requires a separate authorized handoff. |

Advance through these gates in order. Local API tests do not establish email
delivery, a working public interface, actual settlement or production readiness.

## Reuse and data boundaries

- `home_app.py` is a separate application factory. It imports no Hiring routes.
  Hiring's `app.py`, global migration runner and frontend are unchanged.
- `middleware.auth.require_identity` verifies the same Firebase identities.
  Existing `require_auth` retains Hiring's employer approval rules. Identity does
  not confer company, Home operator or helper access.
- Existing `users`, `cook_profiles` and `bookings` tables supply core records.
  `home_visits` is a one-to-one Booking extension, not another booking system.
  Only Home's migration permits an unassigned booking. No legacy database restart
  or import of private Hiring profiles or assessment recordings is required.
- Use a separate logical database and application role. Do not connect Home to
  Hiring's database or the retired marketplace database. Reusing an already-running
  staging SQL instance can avoid another always-on instance, subject to its
  connection budget. A separate database is not a separate cloud security boundary;
  scope runtime IAM, backup access and SQL credentials independently.
- Customers see their own visits; eligible assigned helpers see only agreed visit
  instructions and service addresses; Home operators see the operational queue.
  Lists omit addresses and instructions. No employer API receives household data.
- Cooking assignment requires an approved Home CookProfile and explicit cooking
  permission. Cleaning requires an explicit cleaning permission. A knife-skill
  assessment is not evidence of cleaning suitability. Helper onboarding and its
  operational approval checks remain a later interface gate.
- Do not solicit diagnoses. Allergy and meal instructions can still be sensitive.
  Retention/export/deletion and support escalation need a reviewed Home policy
  before collecting real household information. Existing assessment retention is
  preserved and does not govern these records.

## API contract

All paths start with `/api/home`. Protected routes require a Firebase bearer
token with a verified email. The current backend supports verified-email
accounts; phone-only and delegated family access are not implemented here.
Phone help in the design must not imply those authentication paths already exist.

| Method and path | Authorization and behavior |
| --- | --- |
| `GET /health` | Public; `disabled` by default, database guard checked when enabled. Always reports payments unavailable. |
| `GET /me` | Verified identity; syncs an inert Home customer identity, returns effective operator/owner access and canonical consent version/text. Never imports a Hiring role. |
| `POST /visits` | Customer creates their own visit. Requires an `Idempotency-Key`. Returns `{id, version, status}`. |
| `GET /visits?cursor=...` | Scoped list; at most 50 summaries and an opaque next cursor. Only owners/operators see the full queue. |
| `GET /visits/{id}` | Owner of the visit, eligible assigned helper or Home operator. Unknown and inaccessible visits both return 404. |
| `POST /visits/{id}/actions` | Versioned command with an `Idempotency-Key`. Actions below. |
| `PUT /helpers/{uid}/permission` | Home owner only, with an `Idempotency-Key`. Explicit boolean `enabled`, `cooking`, `cleaning`. Helper must first have a Home identity. |
| `GET /visits/{id}/activity?afterVersion=-1` | Home operator only; at most 100 events, pagination by version. Includes actor/action/time, not household notes or contact details. |
| `GET /pricing` | Home operator; current rate-card ID and latest 50 immutable versions. No public price catalog or automatically seeded rates. |
| `POST /pricing` | Home owner only; saves an immutable draft with its expected predecessor. |
| `POST /pricing/{id}/activate` | Home owner only; atomically activates the draft if its predecessor is still current. Body `{}`. |
| `POST /visits/{id}/quotes` | Home operator; issues an immutable, itemized quote for an accepted visit and active rate card. |
| `GET /visits/{id}/quotes/{quoteId}` | Scoped current or historical offer, with its original approvals and a `current` flag. Other households receive 404. |
| `POST /visits/{id}/quotes/{quoteId}/accept` | Assigned helper accepts the quoted work and earnings. |
| `POST /visits/{id}/quotes/{quoteId}/approve` | Customer only, after helper quote acceptance; records the reviewed quote digest. |
| `POST /visits/{id}/materials/reconcile` | Home operator; verifies receipt ownership/generation and records reviewed costs/final tax. Eligible settlement is queued, never sent inside the SQL transaction. |
| `GET/PUT/DELETE /household` | Customer's own saved address/preferences; explicit opt-in and idempotent changes. Existing visit records are independent. |
| `POST /callbacks` | App Check and rate-limited callback intake. In private staging, an acceptance identity is also required. No visit or charge is created. |
| `POST /helpers/apply`, `POST /helpers/{uid}/review` | Home helper application and owner-confirmed capability review. No self-approval. |
| `POST/GET /visits/{id}/receipts` | Private JPEG/PNG evidence, scoped to visit/quote. Only assigned helpers/operators upload. Maximum twenty photos, 8 MB each. |
| `GET /visits/{id}/receipts/{receiptId}` | Authenticated attachment download; no public Firebase bearer token. |
| `POST /account/verification`, `POST /account/reset` | Existing durable account mail with App Check, rate limits and verification resend cooldown. Action codes remain in URL fragments. |
| `GET /callbacks`, `POST /callbacks/{id}`, `GET /helpers` | Private operator queues and versioned callback follow-up. |
| `GET /audit`, `GET /operations` | Home owner only: bounded access/financial records; no private household notes in audit events. |
| `POST/GET /payout-account`, `POST /payout-account/link` | Approved helper's own namespaced Stripe account; separate explicit Connect gate. A transfer is not a confirmed bank payout. |

Create request:

```json
{
  "service": "both",
  "date": "2027-01-15",
  "time": "10:00",
  "durationMinutes": 150,
  "address": "Customer supplied service address",
  "instructions": {
    "preferences": ["allergies", "fragrance_free"],
    "cleaningTasks": ["kitchen"],
    "visitNotes": "Only the instructions agreed for this visit"
  },
  "consent": {
    "version": "home-visit-v2",
    "shareWithAssignedHelper": true
  }
}
```

Dates are interpreted in the configured service timezone, stored with the visit
and returned as `timeZone`. Past, ambiguous and nonexistent local times are
rejected. Duration is 60–480 minutes in 30-minute steps. Address is at most 400
characters; notes at most 1,000. Requests are limited to 16 KiB. Render all returned
text as text, never HTML.

Preference values: `allergies`, `provided_meal_instructions`, `easy_to_chew`,
`label_meals`, `storage_help`, `fragrance_free`, `customer_supplies`, `phone_help`.
Cleaning tasks: `kitchen`, `dishes`, `bathroom`, `floors`, `laundry`, `general_tidy`.
Unknown fields are rejected; client-selected roles, prices and payment status
are never accepted. Consent text is versioned in `services/home_visits.py`; bump
the version if its meaning changes. Each visit stores its own agreed snapshot.

Commands use `{ "action": "review", "version": 0 }`. Supported actions:

- `review`: operator, once, before assignment.
- `assign`: operator, reviewed request, with an eligible `helperId` different
  from the customer. Assignment can change before acceptance; prior helpers lose
  access. The new version invalidates stale screens.
- `accept`: assigned eligible helper only. Booking status becomes `accepted`.
- `cancel`: customer or operator, only before work starts. Closed visits
  cannot be reopened through this command API.
- `report_issue`: authorized visit participant; holds further progress.
- `resolve_issue`: operator only; recorded as a separate audited change.
- `start` / `finish`: assigned helper, with verified payment and the required
  preceding visit state. `confirm`: customer, after the helper finishes.

Completed visits can still report and resolve an issue. An existing issue on a
cancelled visit can be resolved by an operator without reopening the visit.
Cancellation and service edits remain closed. Commands cannot invent a provider
payment or transfer. The quote routes below add offers to the same visit. Lists return `quoteId`
without fetching financial detail; the detail route expands the current `quote`.
Legacy required price fields are zero while unpriced; a quoted visit's estimate
mirrors its maximum quoted offer. These fields never authorize a payment.

`Idempotency-Key` is 16–128 URL-safe alphanumeric/underscore/hyphen characters.
Keep one key for retries of the same command and use a fresh key for a new action.
A repeated key returns the committed result; a changed payload returns 409.
The response contains no instructions or address. Expected versions reject stale
writes with 409. Refresh the visit before offering a new command. A 503 means
retry the same key after the indicated delay, not create a second request.

## Rates and quotes

All mutation routes above require an `Idempotency-Key`. Home's rate cards use the
same immutable-version approach as Hiring's billing catalog, but do not change
subscription plans or create Stripe products. No rate is active at startup.
Only the configured Home owner can save and activate pricing. Initial example
request (illustrative values, not published prices):

```json
{
  "previousId": null,
  "currency": "usd",
  "rates": {"cookingHourlyCents": 4500, "cleaningHourlyCents": 4000},
  "customerFeeBps": 1000,
  "helperCommissionBps": 1500,
  "materialsCapCents": 10000,
  "quoteValidMinutes": 1440
}
```

Hourly rates support 100–100,000 cents; fee/commission basis points support
0–10,000; the overall material allowance supports 0–1,000,000 cents; validity
supports 30–10,080 minutes. These are input bounds, not price or legal guidance.
Use `previousId` from the current active rate card for a replacement. Two drafts
can share a predecessor, but only one can activate against it. To roll back a
rate, save another version using the old settings and the current predecessor.
Changing rates never rewrites an existing quote or approval.

Quote request for a 150-minute cooking/cleaning visit:

```json
{
  "version": 3,
  "rateCardId": "the-current-rate-card-uuid",
  "cookingMinutes": 90,
  "cleaningMinutes": 60,
  "materials": [
    {"category": "ingredients", "label": "Agreed grocery allowance", "capCents": 2500},
    {"category": "supplies", "label": "Agreed cleaning supplies", "capCents": 500}
  ],
  "tax": {
    "amountCents": 0,
    "reviewConfirmed": true,
    "reviewReference": "operator-review-reference"
  }
}
```

Replace the reference placeholders with real IDs. Tax review is mandatory even
when its result is zero. The API records the operator's review; it does not
determine taxability, validate a jurisdiction, certify the review or assume tax
is zero. Applicable tax policy needs approval before real quoting.

Service minutes must match the original service type and total duration, using
half-hour steps. Ingredients require cooking; supplies can include cleaning
products or cooking consumables such as containers and labels. A request with `customer_supplies` cannot
silently acquire a shopping allowance. At most 20 allowances are accepted, each
with a nonempty label, a positive cap and an eligible category. Their sum cannot
exceed the active rate card's material limit.

Each labor line rounds rate × minutes / 60 half up in integer arithmetic. The
customer fee and helper commission apply to labor only, with half-up rounding.
The offer records labor, material caps, customer fee, tax cap and maximum total.
The helper's view separately shows labor after commission and the maximum
material reimbursement. Materials are reimbursed at reviewed cost, not profit.
Customers do not receive internal commission or tax/receipt review references.

Issuing a quote requires operator review, an eligible assigned helper and that
helper's visit acceptance. The offer binds the immutable rate card, helper,
agreed instructions/address/schedule, amounts and expiration to its digest.
Expiration is the earlier of the rate card's validity period and visit start.
The helper then accepts the itemized quote and earnings; only the customer can
approve it afterward. Both routes use `{ "version": 4, "digest": "quoted-digest" }`
with the current visit version. A quote approval is not payment confirmation.
Refresh after each action: helper acceptance increments the visit version before
customer approval. The historical offer route preserves access to earlier agreed
amounts; an old offer cannot be reapproved after replacement.

An issue hold, revoked helper permission, changed scope, expired quote, wrong
digest or stale visit version blocks acceptance. Reissuing an offer selects a
new current quote and requires fresh helper/customer approvals. Previous offers
and approvals remain immutable. If a payment reference exists, reissuing is
blocked until stage 4 provides an explicit void/refund workflow.

After service reaches `pending_confirmation` or `completed`, the operator can
record actual materials by quote `lineId`, `actualCents` and an opaque UUID
`receiptReference`, with `receiptsReviewed: true`, the current `version`,
`quoteId` and another reviewed `tax` object. Every quoted line must appear once;
actual cost cannot exceed its cap and a positive cost needs a receipt reference.
Final reviewed tax cannot exceed its quoted cap. An open issue blocks this step.
The result records the customer final total, unused allowance and actual helper
allocation. It does not mark money refunded, available or paid out.

Receipt photos are normalized to JPEG, stripped of EXIF/GPS and stored under a
private Home prefix with create-only generation preconditions. SQL reserves the
object identity before upload and freezes finalized evidence. Reconciliation
checks quote/visit ownership and exact storage generation with bounded parallel
metadata reads outside SQL. Actual purchase amounts and tax require human review;
there is no automatic receipt parsing. An idempotent replay returns its already
committed result without requiring storage to remain available. Isolated quote
accounting tests seed completion; financial tests exercise the full state machine
with a deterministic provider. Neither is evidence of actual live settlement.

## Connected Home frontend

From `frontend`, run `npm run dev:home` or `npm run build:home`. The independent
entry is `home/` and output is `dist-home/`; neither command overwrites Hiring's
frontend output or registers another service worker. Operator, pricing and helper
payout screens load in separate chunks. Hosting should use a separate controlled
origin: an older Hiring service worker may intercept a new `/home/` prefix.

The frontend uses the existing Firebase module and branded `cookcredit.com` auth
domain. API requests stay on `/api/home`; no runtime-selected API address is
accepted. A loopback Auth emulator is supported only in Vite development, with
an explicit `VITE_HOME_AUTH_EMULATOR_URL`. Cloud startup rejects emulator config.
No private address, allergy notes or form draft is put in browser storage.
Only a validated return route is kept in session storage. Local previews and
staging are `noindex`; this is not an authentication boundary.

Home notices reuse the existing branded AccountEmail transport and durable
retry implementation. A transactional event pointer prevents notification gaps;
mail conversion leaves queue space for verification/reset messages. Messages link
to private records and contain no address, allergy instruction, phone number,
receipt image or hosted payment URL. Verification/reset links are generated at
delivery, never persisted. `HOME_EMAILS_ENABLED=1` requires App Check and the
existing authenticated CookCredit Workspace mail transport. The agreed public
inquiry/Reply-To address is `connectwithus@cookcredit.com`; its separate mailbox
does not need a new sending credential. The authenticated From address remains
unchanged. Reuse the deployed secret reference; do not create another sender or
claim that a Reply-To change also changed the authenticated From address.

## Runtime and migration controls

Default: `HOME_SERVICES_ENABLED` unset. To prepare isolated staging:

1. Provision a dedicated `cookcredit_home_staging` database and separate
   `cookcredit_home_migrator`/`cookcredit_home_app` roles on approved capacity.
   Neither role should own a Hiring database or inherit other product roles.
   Provision PostGIS with the database owner. Do not activate stopped databases.
2. Set `COOKCREDIT_PRODUCT=home-services` and `HOME_DATABASE_URL` using the
   migrator role from a secret reference. From `backend`, run
   `python -m home.migrate`. It creates only the reused core tables and Home
   extension tables. Migrations are transactional and serialized. They are never
   discovered by `migrations/run_migrations.py`.
3. Run the separate Home container with the app role, `HOME_SERVICES_ENABLED=1`,
   verified `HOME_OWNER_EMAILS`, optional `HOME_OPERATOR_EMAILS`,
   `HOME_SERVICE_TIMEZONE` (default `America/New_York`), explicit HTTPS
   `HOME_FRONTEND_ORIGINS`, existing Firebase configuration and shared Redis rate
   limit storage. Keep secrets out of the repo. Start
   `gunicorn 'home_app:create_app()'`; do not replace Hiring's entrypoint.
4. Keep minimum instances zero and cap workers, instances and SQL pools within
   the existing instance's connection budget. This code does not provision paid
   capacity or deploy a service. Validate IAM, SQL grants, TLS/private access and
   quotas before exposing staging.

The app role receives SELECT/INSERT/UPDATE only on operational tables and
SELECT/UPDATE on the pricing pointer. Events, command history, rate cards, quotes,
helper acceptances, customer approvals and reconciliations receive SELECT/INSERT
only. Startup and health verify the required Home migration marker, not merely
database connectivity. The app role must not own append-only tables or
have inherited UPDATE/DELETE privileges. Use the migrator for reviewed retention
operations. Stage 7 must verify these actual deployed privileges.

## Verification and observability

`tests/test_home_visits.py` uses disposable localhost PostgreSQL schemas owned by
`cookcredit_test`, selected only by `HOME_TEST_DATABASE_URL` or the existing
`HIRING_TEST_DATABASE_URL`. It rejects non-local targets and other identities.
CI's existing PostGIS service can run it without another database service.
Run from the repository root:

```text
python -m pytest backend/tests/test_home_visits.py -q
```

`tests/test_home_quotes.py` also covers pricing and financial concurrency. Run
both files for Home acceptance. Coverage includes concurrent retries, stale concurrent updates, customer/helper
scope, live helper permission revocation, cooking/cleaning capabilities, consent,
rollback, safe errors and default-off isolation. On a local PostgreSQL install
without PostGIS the fixture omits only unused spatial columns; spatial behavior
is not certified by that run. No household information or payment is used.

Every API response carries a server-generated `X-Request-ID`. Error events record
endpoint, status, duration and exception class, never exception messages, tokens,
request bodies or SQL parameters. The durable audit event commits with the state
change. Events are not a message-delivery acknowledgement. The Home bridge uses
the existing durable delivery patterns; deployed retry/age monitoring still needs
staging acceptance.
Use the existing AccountEmail provider and Home dispatch endpoint. One Home
recovery schedule covers its separate durable queues; Hiring's schedules retain
their own targets. Do not introduce a second mail provider. Mutation commands
ensure the actor exists without rewriting their profile. `/me` handles explicit
profile refresh; this avoids unnecessary writes and cross-participant FK locks.
The welcome event requests a wakeup only when it is newly inserted. Worker
wakeups coalesce in a future two-second window and remaining batches, retry
times and abandoned leases request a follow-up through the same worker. Paused
mail/payment processing does not create a wakeup loop. If the outbox is full and
SMTP makes no progress, unconverted notices back off for thirty seconds while
verification/reset mail keeps its own earlier retry time. Queue failure/age
logging reuses the existing privacy-safe reporter.

`frontend/home/firebase.json` is the separate staging Hosting contract. It routes
`/api/home/**` to Home before the SPA, pins the backend revision, preserves the
branded Google popup policy, disables framing and keeps private navigation out
of referrers. Do not deploy the Hiring Hosting config as Home. The guarded
`scripts/bootstrap_home_staging_db.py` can provision only the named Home database
and non-inheriting roles through one execution of the existing staging admin job;
it cannot restart/resize a database or target Hiring's database. The migration
permission regression uses actual non-owner roles on disposable PostGIS and
checks that runtime startup works while audit/schema mutation fails.

### Release acceptance procedure

CI runs the full backend/deployment and frontend regressions, builds the Home
entry, scans public Git history for secrets and audits installed Python and npm
dependencies. Production npm advisories fail at every severity; build tooling
fails at moderate or higher. Review the reported low-severity tooling findings
as well. The current upstream `deepmerge` chain belongs to the existing Workbox
build tooling, not the shipped Home browser bundle. Do not force npm's proposed
downgrade to an obsolete PWA plugin to hide that finding.

Home reuses the existing bounded browser error reporter and confirmed file-save
utility. Diagnostics contain categories and references, never account action
codes, visit URLs, household details or raw error text. A download fallback is
reported as requested; only a completed file write is reported as saved.

Before enabling public Home access, record these results privately against the
exact deployed revision:

1. Check every customer/helper/operator screen and action in a supported desktop
   and mobile browser, including keyboard focus, back/refresh, expired links,
   retries, cancellation and issue holds. Verify an email link opened in another
   tab returns to the intended request or visit after sign-in.
2. Verify actual welcome, verification/reset and visit-message receipt through
   the existing sender, without leaking household instructions in messages.
3. Complete a controlled visit from request, manual helper approval/assignment
   and itemized quote through both approvals, work completion, customer
   confirmation and receipt reconciliation. Confirm the browser saved a receipt.
   A local fake provider verifies state transitions, not live money movement.
4. Verify deployed identity/App Check settings, cross-household access denial,
   helper revocation, database grants, private object access, immutable audit,
   exact origins, shared rate limits and secret scope. Local tests do not certify
   actual cloud IAM or prove absence of compromise.
5. Verify signed webhook handling, retry/recovery, queue age alerts and rollback.
   Keep payments unpaid unless a real transaction is separately authorized.
   Checkout redirect, payment confirmation, refund, transfer and bank payout are
   separate acceptance outcomes; never infer one from another.

Keep Home disabled or private while any required deployed acceptance is open.
Do not publish household records, test identities, tokens or operational evidence
in the source repository.
