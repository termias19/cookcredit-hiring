/* eslint-disable react-refresh/only-export-components -- context module exports the provider
   alongside its useNotifications() hook (same pattern as AuthContext/LangContext). */
/**
 * Notification context — beam-aware unread count.
 *
 * Source of truth is the backend (Postgres), polled on focus + a slow interval; a foreground
 * FCM message bumps the count immediately. Background notifications are handled by the separate
 * public/firebase-messaging-sw.js service worker.
 *
 *   cook  -> number of open beams waiting in their city inbox
 *   eater -> number of their open beams that have at least one responder
 */
import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import { auth, getMessagingIfSupported } from '../firebase'
import { useAuth } from './AuthContext'
import { BEAM_ENABLED } from '../config'
import { getBeamInbox, getMyBeams } from '../utils/Api'

const NotificationContext = createContext({ unreadCount: 0, refresh: () => {}, notifications: [] })
export const useNotifications = () => useContext(NotificationContext)

export function NotificationProvider({ children }) {
  const { user, profile } = useAuth()
  const [unreadCount, setUnreadCount] = useState(0)

  const roles = profile?.roles || []
  const activeRole = profile?.activeRole || profile?.active_role || 'eater'
  const isCook = activeRole === 'cook' && roles.includes('cook')

  // Promise/.then form (not async/await) so setUnreadCount lives inside a deferred callback —
  // matches the BrowseScreen pattern and keeps this callable from the effect without a
  // synchronous setState. cook -> open inbox size; eater -> own open beams that have responders.
  const refresh = useCallback(() => {
    if (!user || !BEAM_ENABLED) return undefined   // value is reset to 0 below when no user
    const p = isCook ? getBeamInbox({ auth, page: 1 }) : getMyBeams({ auth, page: 1 })
    return p.then(d => {
      const beams = Array.isArray(d?.beams) ? d.beams : []
      setUnreadCount(isCook
        ? beams.length
        : beams.filter(b => b.status === 'open' && (b.responseCount || 0) > 0).length)
    }).catch(() => { /* best-effort badge — ignore transient errors */ })
  }, [user, isCook])

  // Poll on mount, on window focus, and slowly in the background.
  useEffect(() => {
    refresh()
    if (!user || !BEAM_ENABLED) return
    const onFocus = () => refresh()
    window.addEventListener('focus', onFocus)
    const id = setInterval(refresh, 60000)
    return () => { window.removeEventListener('focus', onFocus); clearInterval(id) }
  }, [user, refresh])

  // Foreground push: bump the count the instant a beam message arrives.
  // Messaging resolves lazily (dynamic import) so FCM stays off the boot path.
  useEffect(() => {
    let unsub = null
    let live = true
    ;(async () => {
      const messaging = await getMessagingIfSupported()
      if (!messaging || !live) return
      const { onMessage } = await import('firebase/messaging')
      if (!live) return
      unsub = onMessage(messaging, (payload) => {
        const type = payload?.data?.type
        if (type === 'beam' || type === 'beam_chosen') setUnreadCount(c => c + 1)
      })
    })()
    return () => { live = false; try { unsub?.() } catch { /* ignore */ } }
  }, [])

  return (
    <NotificationContext.Provider value={{ unreadCount: user ? unreadCount : 0, refresh, notifications: [] }}>
      {children}
    </NotificationContext.Provider>
  )
}
