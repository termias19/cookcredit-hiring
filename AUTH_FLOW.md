# Hiring account entry

Email signup asks for name, email and password. Google sign-in uses the existing Firebase project and provider; it creates a missing Hiring profile without overwriting an existing one. Firebase verification status is still required. Account linking is delegated to Firebase; the client never merges identities by email.

The selected employer/applicant journey survives sign-in and verification. Applicant invitations retain the role and invitation query. An employer without approval sees the existing access-request form, not an applicant dashboard. Approval remains controlled by the owner. An approved employer creates their own company workspace, with activation serialized per user to prevent duplicate workspaces. API membership and company-scoping checks remain authoritative.

Verification resend has a rolling 60-second cooldown, in addition to the existing API rate limits. A suppressed request returns 429 and Retry-After rather than claiming another message was queued. Already-verified accounts are identified separately. Newly queued account mail requests a post-commit wakeup through the existing Cloud Tasks queue and authenticated mail worker. The existing scheduler recovers missed wakeups and delivery retries. SMTP acceptance is not proof of inbox receipt.

The verification link retains its explicit confirmation button so automated email scanners cannot consume it. After confirmation, a matching signed-in account continues automatically. Returning to an existing verification tab also checks status on focus; no continuous polling is added.

Acceptance still requires real Google sign-in and email inbox receipt, plus company setup with a separate approved employer identity. Automated tests do not establish those external outcomes.

Google profile creation passes the selected intent directly to the existing sync
request. Browser storage is recovery only; restricted storage cannot silently
convert a new employer into an applicant. Account recovery only replays a draft
bound to that Firebase UID and only self-heals a missing (404) profile. Standalone
assessment and assessment-sharing destinations select applicant signup too.
