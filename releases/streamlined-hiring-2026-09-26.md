# Streamlined hiring workflow — 26 September 2026

Hiring managers previously navigated separate team, integration, billing, company and shortlist pages, with duplicate mobile menus. Applicants saved their details, opened a separate application page, clicked again to start the assessment, and later clicked through a separate return page.

This release groups manager work into Roles, Applicants and Settings. Existing company, team, integration and billing components are reused inside Settings. Saved applicants are a view inside Applicants. Legacy URLs redirect with query parameters preserved. Role requirements are collapsible and empty pipeline columns are omitted; all applicants, review controls and saved criteria remain available.

Applicants now save and open the existing assessment in one action. An unsuccessful launch retains the saved application and offers retry. Existing applications resume in place without creating an attempt automatically. Assessment return resolves the server-authorized application and opens its existing status screen. Saved details and withdrawal controls remain available under expandable sections.

- Source: `466fd94b26d1446225512631352c4f8db39f99e1`
- Hosting: `sites/cookcredit-hiring/versions/cde0753ae8e98a48`
- Rollback: `sites/cookcredit-hiring/versions/99aed239927de541`
- Backend unchanged: `cookcredit-hiring-00004-mxr`
- 74 frontend tests passed; backend CI passed 571 tests, 17 skipped. Changed-file lint, production build and secret scans passed.
- CI: https://github.com/termias19/cookcredit-hiring/actions/runs/36280988597
- All 33 assessment/overlay assets and Hosting configuration are unchanged. Development preview is disabled in production.
- No changes to the main website, Toque, scoring formulas, consent text, permission gates, existing records, payments or branded mail.

Fresh production applicant email verification, personal consent, recording submission and employer playback still require acceptance. This release does not declare the platform launch-ready.
