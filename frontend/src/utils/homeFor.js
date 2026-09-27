// Navigation intent never grants a role. BusinessRoute and the API authorize
// workspace access using the server profile and organisation membership.
export function isBusinessProfile(profile) {
  return profile?.employerAccessAllowed === true && (profile?.roles || []).includes('business')
}

export function homeFor(profile) {
  if (isBusinessProfile(profile)) return '/business/roles'
  if (profile?.employerAccessAllowed === true && (profile?.activeRole || profile?.active_role) === 'business') return '/business/onboarding'
  return '/applications'
}

const DESTINATIONS = [
  /^\/business\/role\/[A-Za-z0-9_-]+\/edit$/,
  /^\/owner\/access$/,
  /^\/(profile|applications|assessment)$/,
  /^\/application\/[A-Za-z0-9_-]+$/,
  /^\/apply\/[A-Za-z0-9_-]+$/,
  /^\/application-assessment-return\/[A-Za-z0-9_-]+$/,
  /^\/assessment-sharing\/[A-Za-z0-9_-]+\/[A-Za-z0-9_-]+$/,
  /^\/business\/(onboarding|profile|roles|candidates|shortlists|team|billing|integrations)$/,
  /^\/business\/(role|candidate|invite)\/[A-Za-z0-9_-]+$/,
]

/** Only CookCredit destinations survive authentication, including invitation
 * query strings. Old service/identity routes and external redirects do not. */
export function safeAuthDestination(value) {
  const raw = typeof value === 'string' ? value : value?.pathname
    ? `${value.pathname}${value.search || ''}${value.hash || ''}` : ''
  if (!raw.startsWith('/') || raw.startsWith('//') || raw.includes('\\')) return null
  try {
    const url = new URL(raw, 'https://cookcredit.invalid')
    if (url.origin !== 'https://cookcredit.invalid' || !DESTINATIONS.some(pattern => pattern.test(url.pathname))) return null
    return `${url.pathname}${url.search}${url.hash}`
  } catch { return null }
}

export function rememberDestination(value) {
  const dest = safeAuthDestination(value)
  try {
    if (dest) sessionStorage.setItem('postAuthDest', dest)
    else sessionStorage.removeItem('postAuthDest')
  } catch { /* Navigation still works when browser storage is unavailable. */ }
  return dest
}

// React may render guards repeatedly. Consume intent only after arrival.
export function pendingDest() {
  try { return safeAuthDestination(sessionStorage.getItem('postAuthDest')) } catch { return null }
}

export function clearPendingDestination(arrivedAt) {
  try {
    if (!arrivedAt || pendingDest() === arrivedAt) sessionStorage.removeItem('postAuthDest')
    localStorage.removeItem('cc_pending_onboarding')
    const saved = JSON.parse(localStorage.getItem('cc_account_destination') || 'null')
    if (!arrivedAt || saved?.destination === arrivedAt) localStorage.removeItem('cc_account_destination')
  } catch { /* unavailable storage */ }
}

export function authDestination(profile, requested, uid = profile?.id) {
  let saved
  try { saved = JSON.parse(localStorage.getItem('cc_account_destination') || 'null') } catch { /* optional */ }
  const destination = safeAuthDestination(requested) || (uid && saved?.uid === uid ? safeAuthDestination(saved?.destination) : null) || pendingDest()
  if (profile && destination?.startsWith('/business/') && !destination.startsWith('/business/invite/') && profile.employerAccessAllowed !== true) return '/applications'
  if (profile && destination === '/owner/access' && profile.isAccessOwner !== true) return '/applications'
  return destination || homeFor(profile)
}

export function rememberAccountDestination(uid, value) {
  const destination = safeAuthDestination(value)
  if (!uid || !destination) return
  try { localStorage.setItem('cc_account_destination', JSON.stringify({ uid, destination })) } catch { /* optional */ }
}
