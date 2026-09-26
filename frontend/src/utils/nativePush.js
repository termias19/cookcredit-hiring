/**
 * Native push bridge (Capacitor) — used ONLY inside the native Android/iOS shell.
 *
 * On the web this module is intentionally NOT imported (web push lives in
 * utils/pushNotifications.js). When the app runs inside a Capacitor native shell, call
 * registerNativePush(getIdToken) after login: it asks for the OS notification permission,
 * registers with FCM (Android) / APNs (iOS), and persists the device token through the SAME
 * backend field as web (PATCH /api/auth/me { fcmToken }), so the server send path in
 * backend/services/notifications.py is unchanged.
 *
 * Every Capacitor import is DYNAMIC so this file is inert and build-safe even when the
 * @capacitor/* packages are not installed and on the web (where it is never imported).
 *
 * To wire it up once Capacitor is added (see CAPACITOR.md), call it from AuthContext.fetchProfile
 * for the native case, e.g.:
 *     import { isNativePlatform, registerNativePush } from '../utils/nativePush'
 *     if (await isNativePlatform()) registerNativePush(() => firebaseUser.getIdToken())
 *     else requestNotificationPermission(firebaseUser.uid, null)
 */
const BASE = import.meta.env.VITE_API_URL || 'http://localhost:5000'

export async function isNativePlatform() {
  try {
    const { Capacitor } = await import('@capacitor/core')
    return Capacitor.isNativePlatform()
  } catch {
    return false
  }
}

export async function registerNativePush(getIdToken) {
  if (!(await isNativePlatform())) return
  try {
    const { PushNotifications } = await import('@capacitor/push-notifications')

    const perm = await PushNotifications.requestPermissions()
    if (perm.receive !== 'granted') return

    PushNotifications.addListener('registration', async (token) => {
      try {
        const idToken = await getIdToken?.()
        if (!idToken) return
        await fetch(`${BASE}/api/auth/me`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${idToken}` },
          body: JSON.stringify({ fcmToken: token.value }),
        })
      } catch { /* token persist is best-effort */ }
    })
    PushNotifications.addListener('registrationError', () => { /* ignore; inbox is the fallback */ })

    await PushNotifications.register()
  } catch {
    /* @capacitor/push-notifications not installed yet — no-op until CAPACITOR.md is followed */
  }
}
