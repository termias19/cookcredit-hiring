# Hiring security model

Report suspected vulnerabilities privately to **connectwithus@cookcredit.com**.
Do not post credentials, applicant records, recordings, or working exploit details
in public issues. This document describes implementation, not certification or an
independent penetration-test result.

## Identity and authorization

Firebase authenticates accounts. The API verifies Firebase ID tokens with revocation
checking and caches verified claims for at most 30 seconds, bounded by token expiry.
The frontend's selected journey and saved destination grant no permissions.
Email verification, employer approval, account role, company membership and seat
permission are separate checks. Google sign-in does not bypass them or merge users
by email. Apple sign-in is not implemented in this release.

Employer approval is an owner-controlled gate. An approved employer's activation
creates a separate company and an admin membership. Activation locks the user row;
repeated requests reuse the workspace. Invitation acceptance also locks the user
row and rejects membership in a second company. There is no multi-company selector.

| Seat | Company and role list | Applicant records and consented evidence | Role edits and human review | Company settings, team, integrations, billing |
| --- | --- | --- | --- | --- |
| Admin | Yes | Yes | Yes | Yes |
| Hiring manager | Yes | Yes | Yes | No |
| Recruiter | Yes | Yes | Yes | No |
| Viewer | Yes | No | No | No |

`backend/routes/business.py` derives the company from the authenticated user's
membership, checks `SEAT_PERMISSIONS`, and resolves role IDs within that company.
Hiring application routes independently scope application access to its owner or
authorized employer. A UUID alone never authorizes access. Platform-owner approval
and pricing controls are separate from a company admin seat.

Invitations are expiring, email-bound credentials stored as hashes. Seat capacity
is checked under a company lock. **Current limitation:** with employer approvals
enabled, an invited teammate also needs owner-approved employer access. An
invitation alone does not bypass the platform approval gate. Admins can change a
member's seat role or remove their membership in Settings > Team. The API scopes
the target to the caller's company, serializes membership changes under the company
lock, rechecks the acting admin after acquiring that lock, and protects the last
admin. Removal blocks subsequent workspace requests; it does not erase the person's
account or invalidate previously issued, short-lived media URLs.

## Applicant evidence

Candidate recordings require an active applicant sharing grant for the caller's
company and a terminal assessment attempt. Playback returns short-lived signed
URLs for pinned storage objects. The evidence access endpoint records issuance in
`AssessmentAccessLog`; this is not proof that a browser watched the recording.
Withdrawal/revocation prevents new playback URLs; already issued URLs remain valid
until expiry. CV access is checked separately through the hiring application.
Private reviewer notes are excluded from applicant responses.

The published learning assessment and scoring formulas are preserved. Recordings
and measurements support human review; this platform does not claim independently
validated automatic employment screening.

## Audit coverage and limits

Existing records are retained in their respective systems:

- `HiringAccessEvent`: owner access decisions and requests.
- `HiringApplicationEvent`: application lifecycle and human review events.
- `AssessmentAccessLog`: employer playback URL issuance.
- `SkillAttemptEvent`: assessment processing events.
- `AedtAuditLog`: historical match snapshots, not a general security log.
- `CampaignEvent`: owner marketing campaign changes.
- Durable email, Stripe-event and webhook delivery records: processing and retries.

`WorkspaceActivity` adds transactionally recorded member changes, invitation
creation/acceptance/revocation, company edits, role creation/edits/status changes,
company branding/embed configuration changes, API key creation/revocation, webhook
creation/status changes and manual delivery replay requests. Credentials, webhook
URLs and delivery payloads are excluded from activity details. Settings > Activity log is
admin-only and company-scoped with bounded cursor pagination. Activity writes fail
the associated transaction if they cannot be saved. There is no edit/delete API.
Existing applicant and evidence events are not copied into a second event store.

Admins can filter by event type and export the latest 50 matching records as JSON.
The export rechecks current server authorization and includes a continuation cursor
when more records exist; it is not a full-history archive. The API also supports an
exact actor-ID filter.

These are **not a complete, immutable company audit trail**. Authentication failures
and billing are not yet unified in this view. Historical administrative actions are not reconstructed. There is no independently verified tamper-evident archive. The public
`/business/audit` page explains assessment evidence; it is not an activity log.
Do not describe these controls as SOC 2 certification or a completed security audit.

## Integration boundaries

API keys are scoped to a company and environment, stored as hashes, and revocable.
Webhook delivery uses the existing durable queue, signatures and bounded retries;
receivers must deduplicate event IDs. Retry is not exactly-once delivery.
Billing entitlements depend on verified server-side Stripe events, not the browser
return page. Origin allowlists, App Check, rate limits and server authorization are
independent protections; none should be disabled to repair a login failure.

## Release checks

GitHub CI uses an isolated PostgreSQL database for migrations and authorization
regressions, runs frontend behavior tests, and scans for secrets. Never use a
production database for tests. Release source, live traffic allocation and hosting
version must be checked separately: a ready Cloud Run revision may receive no
production traffic.

Before calling the platform ready, record a fresh employer and applicant journey:
email receipt and verification, correct workspace/application return, consented
recording and submission, employer retrieval/playback, CV save, teammate acceptance,
customer webhook receipt, and subscription payment plus confirmation email.
Automated tests and SMTP acceptance cannot establish these real customer outcomes.
