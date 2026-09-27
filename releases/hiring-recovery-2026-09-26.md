# Hiring recovery controls — 26 September 2026

CV downloads now offer a destination picker where supported, report a successful save only after the file write completes, and distinguish cancellation, errors and unconfirmed browser download requests. Original PDF access rules remain unchanged.

Team settings now recover from load failures, provide a selectable invitation link if copying fails, and distinguish mail-provider acceptance from inbox receipt. Workspaces without the existing invitation entitlement see an availability explanation instead of a form the backend will reject. This does not enable included team invitations or repair invitation delivery.

82 frontend tests, changed-file lint, production build, secret scan and full CI passed. A local browser checked the entitled Team fixture. Production release identity and backend database health passed after deployment. Fresh applicant signup, inbox delivery, consent, recording, submission, employer playback, a saved CV, live team invitations, embedding and webhooks remain acceptance gates. No mass-capacity certification is claimed.

All 33 original assessment/overlay assets and Hosting configuration are preserved. Backend, scoring, consent, data, main website and Toque are unchanged.

Source: `c3844d42a38a48529390654ed24278e4b8ae9de7`

Hosting: `sites/cookcredit-hiring/versions/655f3bb2bcfff753`

Rollback: `sites/cookcredit-hiring/versions/cde0753ae8e98a48`

CI: https://github.com/termias19/cookcredit-hiring/actions/runs/36282466841
