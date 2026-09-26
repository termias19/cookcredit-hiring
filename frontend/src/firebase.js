import { initializeApp, getApps, getApp } from 'firebase/app'
import { getAuth } from 'firebase/auth'

// Firebase WEB config is public-by-design (it ships in the client bundle), so it lives in
// VITE_FIREBASE_* env vars and defaults to the Mise project (foodnlit-1123e).
const US_PROJECT_ID = 'foodnlit-1123e'
// `import.meta.env` is supplied by Vite. The empty fallback also lets the isolated preview
// bundle run under a plain static server while keeping the same public Firebase defaults.
const env = import.meta.env || {}

export const firebaseConfig = {
  apiKey:            env.VITE_FIREBASE_API_KEY             || 'AIzaSyAHVJ-y1JkGTWUA-ONEpPWQ0KWQ08YHyX8',
  authDomain:        env.VITE_FIREBASE_AUTH_DOMAIN         || 'foodnlit-1123e.firebaseapp.com',
  projectId:         env.VITE_FIREBASE_PROJECT_ID          || US_PROJECT_ID,
  storageBucket:     env.VITE_FIREBASE_STORAGE_BUCKET      || 'foodnlit-1123e.firebasestorage.app',
  messagingSenderId: env.VITE_FIREBASE_MESSAGING_SENDER_ID || '319305393408',
  appId:             env.VITE_FIREBASE_APP_ID              || '1:319305393408:web:156dd95582a241938ebfe5',
}

// Per-project Web Push certificate (Console -> Cloud Messaging -> Web Push certificates).
// Project-specific, so it is env-driven alongside the config above.
export const vapidKey =
  env.VITE_FIREBASE_VAPID_KEY ||
  'BIsIuB-bxyoqu4Cxt81S6Ix-6Lg3pEv4qlEDOUzhoj3jGLvxFiRoOdbEy5revj-TZgiysbJODPKveQJk5uDlfOY'

// Guard against Vite HMR re-initializing the app on every hot reload
const app = getApps().length === 0 ? initializeApp(firebaseConfig) : getApp()
export const auth = getAuth(app)
// Firestore and Storage are intentionally NOT initialized: data lives in Postgres via
// the API and uploads go through backend signed URLs, so neither belongs in the boot
// bundle. If a future feature needs one, dynamic-import it at the call site.

// App Check is required by the account API in staging/production. Firebase Auth
// independently enforces its configured reCAPTCHA Enterprise sign-in policy.
let appCheckPromise
export async function getAppCheckHeaders() {
  const siteKey = env.VITE_RECAPTCHA_ENTERPRISE_SITE_KEY
  if (!siteKey) {
    if (import.meta.env.DEV) return {}
    throw new Error('Account security is not configured. Please contact CookCredit support.')
  }
  if (!appCheckPromise) {
    appCheckPromise = import('firebase/app-check').then(({ initializeAppCheck, ReCaptchaEnterpriseProvider, getToken }) => {
      const instance = initializeAppCheck(app, { provider: new ReCaptchaEnterpriseProvider(siteKey), isTokenAutoRefreshEnabled: true })
      return { instance, getToken }
    })
  }
  const { instance, getToken } = await appCheckPromise
  const { token } = await getToken(instance)
  return { 'X-Firebase-AppCheck': token }
}

/**
 * FCM messaging, resolved LAZILY (dynamic import + isSupported()) so the
 * messaging module and its support probe stay off the first-paint critical
 * path — the old top-level `await isSupported()` blocked module evaluation.
 * Resolves to the Messaging instance or null (unsupported browser).
 */
let messagingPromise = null
export function getMessagingIfSupported() {
  if (!messagingPromise) {
    messagingPromise = import('firebase/messaging')
      .then(({ isSupported, getMessaging }) => isSupported().then((ok) => (ok ? getMessaging(app) : null)))
      .catch(() => null)
  }
  return messagingPromise
}
