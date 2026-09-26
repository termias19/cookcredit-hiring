import { auth, firebaseConfig, vapidKey, getMessagingIfSupported } from '../firebase'

const BASE = import.meta.env.VITE_API_URL || 'http://localhost:5000'

// Register the background-message worker with THIS market's Firebase config in the query string.
// A service worker can't read Vite's import.meta.env, so we hand it the active project's config at
// registration time; an ET build then pushes from the Addis project, not the US one. Returns a
// ServiceWorkerRegistration to pass to getToken(), or undefined to fall back to the FCM SDK's
// default registration (which uses the worker's own US fallback config).
async function registerMessagingSW() {
  if (!('serviceWorker' in navigator)) return undefined
  try {
    const qs = new URLSearchParams({
      apiKey: firebaseConfig.apiKey,
      authDomain: firebaseConfig.authDomain,
      projectId: firebaseConfig.projectId,
      storageBucket: firebaseConfig.storageBucket,
      messagingSenderId: firebaseConfig.messagingSenderId,
      appId: firebaseConfig.appId,
    }).toString()
    return await navigator.serviceWorker.register(`/firebase-messaging-sw.js?${qs}`)
  } catch {
    return undefined
  }
}

// Last token we successfully sent to the backend, cached locally so we don't PATCH on every
// app load. This REPLACES the old Firestore read of users/{uid}.fcmToken — Firestore is no
// longer the source of truth; the token lives in Postgres via PATCH /api/auth/me.
const TOKEN_CACHE_KEY = 'cc_fcm_token'

/**
 * Request notification permission (if not already decided), obtain the current FCM token, and
 * persist it to the backend (users.fcm_token) only when it has changed. Safe to call on every
 * app load: it no-ops on non-HTTPS (localhost), unsupported browsers, or a denied permission,
 * and getToken() is cheap once permission is granted.
 *
 * Android (the common phone in Addis) gets reliable push; iOS web-push needs the PWA installed
 * to the home screen (iOS 16.4+). The first param is kept for call-site compatibility (it was
 * the Firestore uid) and is unused now that the stored token is cached locally.
 */
export async function requestNotificationPermission(_uid, storedToken = null) {
  if (location.protocol !== 'https:') return null   // FCM requires HTTPS; skip on localhost
  if (!('Notification' in window)) return null       // very old browser
  if (Notification.permission === 'denied') return null // user already blocked it

  try {
    const messaging = await getMessagingIfSupported()
    if (!messaging) return null                      // browser doesn't support FCM

    const permission = await Notification.requestPermission()
    if (permission !== 'granted') return null

    const { getToken } = await import('firebase/messaging')
    const swReg = await registerMessagingSW()
    const token = await getToken(messaging, swReg
      ? { vapidKey, serviceWorkerRegistration: swReg }
      : { vapidKey })
    if (!token) return null

    let cached = storedToken
    if (cached == null) {
      try { cached = localStorage.getItem(TOKEN_CACHE_KEY) } catch { cached = null }
    }
    if (token !== cached) {
      const idToken = await auth.currentUser?.getIdToken().catch(() => null)
      if (idToken) {
        const res = await fetch(`${BASE}/api/auth/me`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${idToken}` },
          body: JSON.stringify({ fcmToken: token }),   // fcmToken is the whitelisted PATCH field
        }).catch(() => null)
        if (res && res.ok) {
          try { localStorage.setItem(TOKEN_CACHE_KEY, token) } catch { /* ignore */ }
        }
      }
    }
    return token
  } catch (err) {
    console.error('Push notification setup failed:', err)
    return null
  }
}

/**
 * Revoke push for this device on sign-out: null the token server-side (while the
 * session is still valid), invalidate the FCM registration, and drop the local
 * cache. Best-effort on every step — sign-out must never be blocked by push
 * cleanup — but without this the backend keeps routing the former user's
 * notifications to this device.
 */
export async function revokeNotificationToken() {
  try { localStorage.removeItem(TOKEN_CACHE_KEY) } catch { /* ignore */ }
  try {
    const idToken = await auth.currentUser?.getIdToken().catch(() => null)
    if (idToken) {
      await fetch(`${BASE}/api/auth/me`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${idToken}` },
        body: JSON.stringify({ fcmToken: null }),
      }).catch(() => null)
    }
  } catch { /* ignore */ }
  try {
    const messaging = await getMessagingIfSupported()
    if (messaging) {
      const { deleteToken } = await import('firebase/messaging')
      await deleteToken(messaging)
    }
  } catch { /* ignore */ }
}
