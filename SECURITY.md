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
invitation alone does not bypass the platform approval gate. Existing memberships
do not yet have a self-service role-change/removal UI; do not promise this capability.

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

These are **not a complete, immutable company audit trail**. Company profile edits,
role configuration edits, invitation revocation and integration configuration do
not all have a common actor/time/change history. There is no company audit-log
export or independently verified tamper-evident archive. The public
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
