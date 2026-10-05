# CookCredit presentation and journey boundaries

The public website and Hiring use warm paper, dark brown text, rust accents,
Cormorant Garamond headings and Inter body text. Marketing pages can use large
headings and video; account forms and workspaces retain compact, task-focused
layouts. A visual refresh must not replace an existing account or assessment flow.

## Shared sources

- `public-site/cookcredit-warm.css`: public home, About, Contact, learning and Hiring introductions.
- `public-site/fonts/`: self-hosted Latin font subsets and upstream OFL licenses.
  The files support the main site's existing `style-src 'self'` policy.
- `frontend/src/styles/business-theme.css`: existing Hiring tokens and shared layout styles.
- `frontend/src/styles/access.css`: access requests and owner controls.
- `frontend/src/components/AuthShell.jsx`: login, signup, reset and verification frame.

Keep company-supplied branding separate from interface colors. CSS variables must
not be saved as a company's hexadecimal brand color. Semantic error, warning and
recording-analysis colors retain their meaning.

## Existing service connections

The public site's product links lead to the existing learning assessment, Hiring
application and Toque. Its Sign in menu chooses a product; it does not introduce
central single sign-on or share credentials between products. Contact continues
to use the existing contact service.

Hiring uses its configured API origin and existing Firebase authentication.
Preserve `next` destinations and account-bound pending destinations through
signup, verification and login. Keep workspace authorization on the server.
Never use a design-preview account bypass to validate production access.

Integrations may offer applicant links and widget snippets only for open roles.
When a selected role closes or moves to Trash, its sharing selection must become
invalid immediately. This presentation rule supplements server-side checks.

## Release checks

Build and test the frontend with its reviewed environment configuration. Check
desktop, mobile, keyboard access, motion preferences and visible error states.
Preserve existing main-site assets and published assessment files during hosting
updates; `public-site/` is an overlay, not a complete replacement hosting tree.
Include the warm stylesheet, fonts and font licenses in that overlay.

Visual approval and automated tests do not prove email receipt, a fresh account's
verification return, a real recording upload, employer playback, a completed
payment, or customer webhook delivery. Those require separate end-to-end
acceptance. This document is not a launch-readiness certification.
