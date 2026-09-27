/**
 * BusinessContext — the B2B workspace store, backed by the real org-scoped backend
 * (/api/business/*). On mount it loads the org, the role postings, the org shortlist,
 * and the verified-cook roster, authenticated with the signed-in user's Firebase ID
 * token; mutations write THROUGH to the backend (optimistic where it makes the UI feel
 * instant, then reconciled with server truth). The per-role pipeline is NOT cached
 * globally — the Role screen owns it via getBusinessRole(id) so each card carries the
 * server-of-record match snapshot.
 *
 * Mounted inside BusinessRoute, so a 'business' user is normally present. Under the
 * VITE_BUSINESS_DEV_BYPASS flag there may be no user: the store then stays empty and
 * makes no network calls (the screens render their honest empty states).
 */
/* eslint-disable react-refresh/only-export-components -- a context module intentionally exports
   the provider component alongside its useBusiness() hook (same pattern as LangContext). */
import { createContext, useContext, useState, useCallback, useEffect } from 'react'
import { useAuth } from './AuthContext'
import { useLocation } from 'react-router-dom'
import { workspaceReads } from '../utils/workspaceReads'
import {
  getBusinessOrg, getBusinessRoles, createBusinessRole,
  getBusinessShortlist, toggleBusinessShortlist, moveBusinessStage,
  getBusinessCandidates,
} from '../utils/Api'

const Ctx = createContext(null)
export const useBusiness = () => useContext(Ctx)

export function BusinessProvider({ children }) {
  const { user } = useAuth()
  const location = useLocation()
  const { roles: needRoles, candidates: needCandidates, shortlist: needShortlist } = workspaceReads(location.pathname, location.search)
  const [org, setOrg] = useState(null)
  const [roles, setRoles] = useState([])
  const [shortlist, setShortlist] = useState([])     // cook ids starred for the org
  const [candidates, setCandidates] = useState([])   // verified-cook roster (de-identified for viewer seats)
  const [screeningPolicy, setScreeningPolicy] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [reloadKey, setReloadKey] = useState(0)

  // Always resolve a FRESH id token per call — Firebase tokens expire (~1h) and getIdToken()
  // refreshes transparently when needed. (No long-lived token kept in module state.)
  const getToken = useCallback(async () => {
    if (!user) return null
    try { return await user.getIdToken() } catch { return null }
  }, [user])

  // Initial load: org + roles + shortlist + roster in parallel. Each is independent — one
  // failing (empty workspace, a 403, a transient error) must not blank the others.
  useEffect(() => {
    let live = true
    if (!user) { setLoading(false); return }
    setLoading(true); setError(null)
    ;(async () => {
      const token = await user.getIdToken().catch(() => null)
      if (!live) return
      if (!token) { if (live) { setLoading(false); setError('auth') } return }
      const [orgR, rolesR, slR, candR] = await Promise.allSettled([
        getBusinessOrg({ token }),
        needRoles ? getBusinessRoles({ token }) : Promise.resolve(null),
        needShortlist ? getBusinessShortlist({ token }) : Promise.resolve(null),
        needCandidates ? getBusinessCandidates({ token }) : Promise.resolve(null),
      ])
      if (!live) return
      if (orgR.status === 'fulfilled') setOrg(orgR.value?.org || null)
      if (needRoles && rolesR.status === 'fulfilled') setRoles(Array.isArray(rolesR.value?.roles) ? rolesR.value.roles : [])
      if (needShortlist && slR.status === 'fulfilled') setShortlist(Array.isArray(slR.value?.cookIds) ? slR.value.cookIds : [])
      if (needCandidates && candR.status === 'fulfilled') {
        setCandidates(Array.isArray(candR.value?.candidates) ? candR.value.candidates : [])
        setScreeningPolicy(candR.value?.screeningPolicy || null)
      }
      // The load-bearing reads BOTH failing means the workspace couldn't load at
      // all — surface it so consumers don't render the failure as "empty".
      if (orgR.status === 'rejected' || (needRoles && rolesR.status === 'rejected') || (needCandidates && candR.status === 'rejected')) setError('load')
      setLoading(false)
    })()
    return () => { live = false }
  }, [user, reloadKey, needRoles, needCandidates, needShortlist])

  /** Re-run the workspace load (used by the error-state retry buttons). */
  const refresh = useCallback(() => {
    setLoading(true); setError(null); setReloadKey((k) => k + 1)
  }, [])

  // Create a role (POST) and prepend the persisted row. Returns the new role so the caller
  // can route straight to it. Async — callers must await.
  const addRole = useCallback(async (role) => {
    const token = await getToken()
    if (!token) return null
    const { role: created } = await createBusinessRole({ token, role })
    if (created) setRoles(prev => [created, ...prev])
    return created || null
  }, [getToken])

  // Toggle the org shortlist: optimistic flip, then reconcile with the server's truth; revert on failure.
  const toggleShortlist = useCallback(async (cookId) => {
    if (!cookId) return
    const had = shortlist.includes(cookId)
    setShortlist(prev => (had ? prev.filter(x => x !== cookId) : [...prev, cookId]))
    try {
      const token = await getToken()
      if (!token) throw new Error('no token')
      const { shortlisted } = await toggleBusinessShortlist({ token, cookId })
      setShortlist(prev => {
        const on = prev.includes(cookId)
        if (shortlisted && !on) return [...prev, cookId]
        if (!shortlisted && on) return prev.filter(x => x !== cookId)
        return prev
      })
      return true
    } catch {
      // revert to the pre-toggle membership
      setShortlist(prev => (had
        ? (prev.includes(cookId) ? prev : [...prev, cookId])
        : prev.filter(x => x !== cookId)))
      return false
    }
  }, [getToken, shortlist])

  // Advance a cook in a role's pipeline (POST). The Role screen owns its pipeline view and
  // refetches; this only persists the move.
  const moveStage = useCallback(async (roleId, cookId, stage) => {
    const token = await getToken()
    if (!token) return false
    try { await moveBusinessStage({ token, id: roleId, cookId, stage }); return true }
    catch { return false }
  }, [getToken])

  const value = {
    org, roles, shortlist, candidates, screeningPolicy, loading, error, refresh,
    roleById: id => roles.find(r => r.id === id) || null,
    candidateById: id => candidates.find(c => c.id === id) || null,
    isShortlisted: id => shortlist.includes(id),
    getToken,
    addRole, toggleShortlist, moveStage,
  }
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}
