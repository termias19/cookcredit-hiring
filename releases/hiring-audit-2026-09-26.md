# Hiring functional audit repair — 2026-09-26

Published from the clean public checkout. Frontend source `dc11d93fec900e43e8460fd889945441c6a1ba8c`.

The hiring audit found misleading clipboard success, missing recovery from application-loading failures, stale pagination, premature paid-plan offers, mismatched API/webhook defaults, inaccessible authentication switches, and pay-range validation deferred until server rejection. This release repairs those behaviors without changing the visual design, backend or assessment.

- Hosting version: `sites/cookcredit-hiring/versions/99aed239927de541`
- Previous version for rollback: `sites/cookcredit-hiring/versions/dd41f131ca798c76`
- Backend remains `cookcredit-hiring-00004-mxr`.
- All 33 packaged assessment/overlay assets and Hosting configuration are unchanged.
- 68 frontend tests; 571 backend tests passed, 17 skipped; changed-file lint and secret scans passed.
- CI: https://github.com/termias19/cookcredit-hiring/actions/runs/36277999689

Production acceptance remains incomplete. A fresh applicant must still verify email, consent, record and submit an assessment, and the employer must retrieve and play that submitted evidence. Automated tests and the current owner's workspace checks do not establish those outcomes. This is not a launch-readiness declaration.
