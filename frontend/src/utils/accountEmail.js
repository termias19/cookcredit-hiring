/** Native Firebase or our branded delivery outbox, explicitly selected at build
 * time. A custom-provider failure must never send a second native email.
 */
export function createAccountEmail({ auth, sendVerification, sendReset, ready, continueUrl, attest, environment = 'production', provider = 'firebase', request }) {
  function settings(language) {
    if (!ready) throw new Error('Account email is temporarily unavailable. Please try again later.')
    if (!['firebase', 'google_smtp', 'sendgrid'].includes(provider)
        || (provider !== 'firebase' && typeof request !== 'function')) throw new Error('Account email is not configured.')
    const destination = new URL(continueUrl)
    const stagingReturn = environment === 'staging'
      && destination.origin === 'https://cookcredit-hiring-staging.web.app'
      && destination.pathname === '/login'
    if (destination.username || destination.password || destination.search || destination.hash
        || destination.protocol !== 'https:'
        || !(stagingReturn || destination.hostname === 'cookcredit.com' || destination.hostname.endsWith('.cookcredit.com'))) {
      throw new Error('Account email destination is not configured.')
    }
    auth.languageCode = language === 'ES' ? 'es' : 'en'
    return { url: destination.href, handleCodeInApp: false }
  }
  return {
    async verification(user, language) {
      if (!user || user !== auth.currentUser) throw new Error('Sign in to request a verification email.')
      if (user.emailVerified) return
      const options = settings(language)
      await attest()
      if (provider !== 'firebase') return request('verification', user, {})
      await sendVerification(user, options)
    },
    async reset(email, language) {
      const options = settings(language)
      await attest()
      if (provider !== 'firebase') return request('password-reset', null, { email: email.trim() })
      try {
        await sendReset(auth, email.trim(), options)
      } catch (error) {
        // Keep the same visible response on older projects without enumeration
        // protection. Network errors and quota failures must still be shown.
        if (error?.code !== 'auth/user-not-found') throw error
      }
    },
  }
}
