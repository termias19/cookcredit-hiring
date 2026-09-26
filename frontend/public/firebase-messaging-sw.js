/* global firebase */
importScripts('https://www.gstatic.com/firebasejs/12.10.0/firebase-app-compat.js')
importScripts('https://www.gstatic.com/firebasejs/12.10.0/firebase-messaging-compat.js')

// Per-market Firebase config. The app registers this worker with the active project's config in
// the query string (a service worker can't read Vite's import.meta.env), so an ET build pushes
// from the Addis project. Falls back to the US / CookCredit project when registered without
// params (e.g. the FCM SDK's own default registration).
function configFromQuery() {
  try {
    const p = new URL(self.location).searchParams
    if (!p.get('projectId')) return null
    return {
      apiKey: p.get('apiKey'),
      authDomain: p.get('authDomain'),
      projectId: p.get('projectId'),
      storageBucket: p.get('storageBucket'),
      messagingSenderId: p.get('messagingSenderId'),
      appId: p.get('appId'),
    }
  } catch {
    return null
  }
}

firebase.initializeApp(configFromQuery() || {
  apiKey: "AIzaSyAHVJ-y1JkGTWUA-ONEpPWQ0KWQ08YHyX8",
  authDomain: "foodnlit-1123e.firebaseapp.com",
  projectId: "foodnlit-1123e",
  storageBucket: "foodnlit-1123e.firebasestorage.app",
  messagingSenderId: "319305393408",
  appId: "1:319305393408:web:156dd95582a241938ebfe5"
})

const messaging = firebase.messaging()

async function isBlockedSender(senderId) {
  if (!senderId) return false
  try {
    const cache = await caches.open('cc-blocked-v1')
    const res = await cache.match('/__blocked_uids__')
    if (!res) return false
    const uids = await res.json()
    return Array.isArray(uids) && uids.includes(senderId)
  } catch {
    return false
  }
}

messaging.onBackgroundMessage(async payload => {
  const { title, body } = payload.notification || {}
  if (!title) return
  const senderId = payload.data?.senderId
  if (await isBlockedSender(senderId)) return
  self.registration.showNotification(title, {
    body: body || '',
    icon: '/icon-192.png',
    badge: '/icon-192.png',
    data: payload.data || {},
  })
})

self.addEventListener('notificationclick', event => {
  event.notification.close()
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(clientList => {
      // Focus existing tab if one is open
      for (const client of clientList) {
        if (client.url.startsWith(self.location.origin) && 'focus' in client) {
          return client.focus()
        }
      }
      // Otherwise open a new tab
      return clients.openWindow('/')
    })
  )
})
