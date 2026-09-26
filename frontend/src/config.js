/**
 * Build-time feature flags.
 *
 * MARKETPLACE_ENABLED gates the in-home booking + pantry transaction layer (booking request,
 * bookings list/detail, payments, pantry/saved-cooks). Those screens are still mock — no backend
 * (no /api/bookings, payments are placeholder) — so they stay HIDDEN while we market the working
 * surface (discover verified cooks, the on-camera skill test, cook listings, the B2B screen).
 * Flip to true once the bookings/payments backend ships, then un-hide the nav tabs + routes.
 *
 * PREVIEW mode (run `VITE_PREVIEW=1 npm run dev`, dev-only) force-enables it so every screen is
 * reachable for a click-through at /preview with a mocked user and no backend. Gated to import.meta.env.DEV
 * so a production build can never turn it on.
 */
export const PREVIEW = import.meta.env.DEV && import.meta.env.VITE_PREVIEW === '1'
export const MARKETPLACE_ENABLED = PREVIEW

/** Single-market build (US) — currency/phone/locale live in utils/region.js. */
export const MARKET = 'US'

/** Published product surfaces. Never send hiring visitors to legacy local screens. */
export const COOKCREDIT_SITE_URL = 'https://cookcredit.com/'
export const COOKCREDIT_ASSESSMENT_URL = 'https://cookcredit-knife-demo.web.app/'

/**
 * BEAM_ENABLED gates the "post a task" broadcast feature (a client broadcasts a one-off task to
 * nearby / city-wide helpers; helpers respond with a note + price; the client picks one). Independent
 * of MARKETPLACE_ENABLED so it ships without un-hiding the still-unbuilt payment layer.
 */
export const BEAM_ENABLED = true
