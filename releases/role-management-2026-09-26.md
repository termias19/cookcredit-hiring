# Hiring role editing, recoverable Trash and workspace improvements

Hiring managers can edit a role using the existing form, move it to Trash, and restore it as closed. Trashing closes its applicant link and preserves applications, CVs, recordings and reviews. Reopening still enforces the workspace role limit. Edits send only changed fields; existing application assessment criteria remain frozen.

The release also routes workspace invitations through the existing bounded branded-mail outbox, includes five team seats for included-access workspaces, removes unused workspace reads and provides optional browser-local PDF text reading. The original PDF and scoring assets remain unchanged.

Validation: 96 frontend tests passed; local backend/deployment tests: 593 passed, 8 skipped; CI backend: 584 passed, 17 skipped. Production build, secret scan, staging and production health/security checks passed. Live role edit, unchanged measurement ranges, Trash filtering, closed applicant link, restore-as-closed, reopening and existing applicant preservation passed. Live PDF text extraction passed. All 33 assessment/overlay assets and Hosting security configuration were preserved.

API minimum remains zero and maximum remains three; no capacity upgrades were made. The isolated 240-applicant workload passed with eight concurrent slots, but adapted identity/mail/webhooks and disposable PostGIS do not establish production throughput.

Fresh applicant inbox verification, real recording/submission/employer playback, browser-confirmed CV save, live teammate invitations, embedding and webhook delivery still need controlled acceptance. This release is not a declaration of full launch readiness.

Backend source: `fa1ed98ddd4dc46fbde0cb38622375e3353614ae`  
Frontend source: `90e3e1571b43673b55d12ca56f465f1ffb46a776`  
Backend revision: `cookcredit-hiring-00005-sp6`  
Hosting: `sites/cookcredit-hiring/versions/9e7531d0e841f1ff`

Rollback: backend `cookcredit-hiring-00004-mxr`; frontend `sites/cookcredit-hiring/versions/655f3bb2bcfff753` for the pre-feature release, or `sites/cookcredit-hiring/versions/2da5f0c9dcd22914` to undo only loading-text correction. Additive migration 028 remains in place during code rollback. Image digests and CI links are in the JSON release record.
