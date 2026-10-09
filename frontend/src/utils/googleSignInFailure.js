import { profileFailure } from './profileFailure.js'

/** Show only bounded provider codes, never provider messages, tokens or emails. */
export function googleSignInFailure(error) {
  if (['auth/popup-closed-by-user', 'auth/cancelled-popup-request'].includes(error?.code)) return ''
  if (error?.status) return profileFailure(error).message
  const code = typeof error?.code === 'string' && /^(auth|appCheck)\/[a-z-]{1,80}$/.test(error.code) ? error.code : null
  const messages = {
    'auth/popup-blocked': 'Allow the Google sign-in window, then try again. You can also use email below.',
    'auth/account-exists-with-different-credential': 'This email already has an account. Use your existing sign-in method below.',
    'auth/unauthorized-domain': 'Google sign-in is not configured for this website. Contact connectwithus@cookcredit.com.',
    'auth/network-request-failed': 'Google could not be reached. Check your connection and try again.',
    'auth/operation-not-supported-in-this-environment': 'Open this page in your regular browser to use Google sign-in.',
  }
  return (messages[code] || 'Google sign-in could not finish. Please try again or use email below.')
    + (code ? ` Reference: ${code}.` : '')
}
