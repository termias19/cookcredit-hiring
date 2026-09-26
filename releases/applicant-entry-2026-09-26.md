# Applicant assessment entry fix — 26 September 2026

Production assessment entry failed before authentication because the pinned hiring bridge allowed staging addresses but omitted the production API and return origin. The backend already generated same-origin assessment links, and the deployed Content Security Policy already allowed the correct production API.

The existing packaging step now binds the pinned bridge to the exact API and return origin for its deployment. Packaging refuses mismatched configuration or changed source anchors. URL validation still rejects foreign origins, credentials, unexpected paths, query strings and fragments; production also rejects staging and localhost addresses. No wildcard or query-derived origin trust was added.

The existing authentication flow retains the invitation when switching accounts from verification, recovering from signup errors, returning through an email action, or loading an account before its profile is ready. The application form explains the sequence and labels its next step as saving the application and continuing to assessment. Visual layout, consent, branded email delivery, scoring and data remain unchanged.

## Validation and deployment

All 60 frontend tests passed. GitHub CI passed 571 backend tests with 17 skips, frontend tests, and the public history secret scan. The public production build passed. The unchanged backend launch function produces a URL accepted by the built bridge. Regression tests exercise both deployment pairs, malformed links, cross-environment rejection and account-bound verification return paths.

The release preserves 32 of 33 assessment/overlay assets byte-for-byte; only hiring-bridge.mjs changes. The published learning site and original scoring files were not deployed or modified. Hosting security/cache configuration, backend revision, infrastructure, database and capacity are unchanged. Exact sources, Hosting version and rollback are in the adjacent JSON; rollback requires only restoring the prior Hosting version.

Live browser verification reproduced CC-HIRING-LINK before the fix. After deployment, the same synthetic-session URL loads the assessment, restores the existing account without a second login, and correctly fails the server's session-ownership check. This is a security/entry smoke test, not a real recording submission.

## Remaining acceptance

The fresh real production applicant journey is still incomplete: inbox delivery and email verification, return to the correct invitation, consent, CV and camera recording submission, then employer retrieval/playback and review. No synthetic result is represented as a real applicant assessment or hiring decision.

The reported professional-cook screen saying “this is a test program” has not been identified. Inspected production-build login and applicant signup screens do not show it. The exact URL is needed to distinguish an obsolete public screen from a staging screen or cached client. Accurate measurement and consent limitations remain intact.

This release fixes assessment entry and return navigation. It does not declare the platform launch-ready.
