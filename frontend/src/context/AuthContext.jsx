/* eslint-disable react-refresh/only-export-components -- this context module intentionally exports
   the AuthProvider component alongside its useAuth() hook (same pattern as LangContext/BusinessContext). */
import { createContext, useContext, useState, useEffect, useMemo, useRef } from 'react'
import {
  createUserWithEmailAndPassword,
  signInWithEmailAndPassword,
  signOut,
  onAuthStateChanged,
  sendEmailVerification,
  sendPasswordResetEmail,
  updateProfile as updateFirebaseProfile,
} from 'firebase/auth'
import { auth, getAppCheckHeaders } from '../firebase'
import { clearPendingDestination } from '../utils/homeFor'
import { revokeNotificationToken } from '../utils/pushNotifications'
import { PREVIEW } from '../config'
import { useLang } from './LangContext'
import { createAccountEmail } from '../utils/accountEmail'
import { completeSignup } from '../utils/completeSignup'

const AuthContext = createContext()
export const useAuth = () => useContext(AuthContext)

const BASE = import.meta.env.VITE_API_URL || 'http://localhost:5000'
const accountEmail = createAccountEmail({
  auth, sendVerification: sendEmailVerification, sendReset: sendPasswordResetEmail,
  ready: import.meta.env.VITE_FIREBASE_EMAIL_BRANDING_READY === '1',
  continueUrl: import.meta.env.VITE_AUTH_EMAIL_CONTINUE_URL || 'https://cookcredit.com',
  attest: getAppCheckHeaders,
  environment: import.meta.env.VITE_DEPLOYMENT_ENVIRONMENT,
  provider: import.meta.env.VITE_AUTH_EMAIL_PROVIDER || 'firebase',
  request: async (kind, account, body) => apiFetch(`/api/auth/email/${kind}`, account ? await account.getIdToken() : null, {
    method: 'POST', body: JSON.stringify(body),
  }),
})

// PREVIEW mode (VITE_PREVIEW=1, dev only): a fully-privileged mock user + profile so every gated
// screen renders for a click-through, with no Firebase login and no backend.
const MOCK_USER = { uid: 'preview-user', email: 'preview@cookcredit.example', emailVerified: true, getIdToken: async () => 'preview-token' }
const MOCK_PROFILE = {
  employerAccessAllowed: true,
  id: 'preview-user', email: 'preview@cookcredit.example', name: 'Preview User', phone: '',
  roles: ['eater', 'cook', 'business'], activeRole: 'cook', photoUrl: null, isAdmin: true, stripeConnected: true,
  eaterProfile: { userId: 'preview-user', addressCity: 'Atlanta', addressState: 'GA', addressStreet: '123 Peachtree St', dietaryPreferences: [] },
  cookProfile: {
    userId: 'preview-user', bio: 'Preview cook — Ethiopian and Southern home cooking.',
    cuisines: ['Ethiopian', 'Southern'], specialties: ['Injera', 'Doro Wat'], pricePerHour: 45, travelRadiusMiles: 15,
    baseCity: 'Atlanta', baseState: 'GA', portfolioPhotos: [], skillVerified: true, skillTier: 'gold', skillScore: 88,
    approved: true, applicationStatus: 'approved', stripeOnboarded: true, dietaryCapabilities: ['halal'], yearsExperience: 8,
  },
}

async function apiFetch(path, token, opts = {}) {
  const protectedAccountAction = path === '/api/auth/sync' || path.startsWith('/api/auth/email/')
  const attestation = protectedAccountAction ? await getAppCheckHeaders() : {}
  const res = await fetch(`${BASE}${path}`, {
    ...opts,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
      ...attestation,
      ...opts.headers,
    },
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    const err = new Error(body?.error || `Request failed (${res.status})`)
    err.status = res.status
    err.code = body?.code
    throw err
  }
  return res.json()
}

/**
 * GET /api/auth/me with a one-shot self-heal: a 404 for a VALID Firebase
 * session means the Postgres row is missing (fresh/restored DB, cross-env dev
 * login). /api/auth/sync is idempotent create-or-update and never grants roles
 * beyond eater client-side, so recreate the row once and refetch.
 */
async function fetchMeWithHeal(firebaseUser) {
  const token = await firebaseUser.getIdToken()
  // A transient signup API failure must not discard the customer's name or
  // employer onboarding intent. Never replay another account's draft.
  let draft
  try { draft = JSON.parse(sessionStorage.getItem('cc_signup_profile') || 'null') } catch { /* unavailable storage */ }
  if (draft?.uid === firebaseUser.uid && draft.profile) {
    await apiFetch('/api/auth/sync', token, { method: 'POST', body: JSON.stringify(draft.profile) })
    try { sessionStorage.removeItem('cc_signup_profile') } catch { /* unavailable storage */ }
  }
  try {
    return await apiFetch('/api/auth/me', token)
  } catch (err) {
    if (err?.status !== 404) throw err
    await apiFetch('/api/auth/sync', token, {
      method: 'POST',
      body: JSON.stringify({
        name: firebaseUser.displayName || (firebaseUser.email || '').split('@')[0] || 'User',
        roles: ['eater'],
        activeRole: 'eater',
        createOnly: true,
      }),
    })
    return apiFetch('/api/auth/me', token)
  }
}

export function AuthProvider({ children }) {
  const { lang } = useLang()
  const [user, setUser]       = useState(PREVIEW ? MOCK_USER : null)
  const [profile, setProfile] = useState(PREVIEW ? MOCK_PROFILE : null)
  const [loading, setLoading] = useState(!PREVIEW)
  // True when the /api/auth/me fetch failed for a signed-in user. Consumers
  // (ProtectedRoute) surface a retry instead of silently routing a cook or
  // business account as a plain eater. Authorization still fails closed —
  // this only makes the failure visible.
  const [profileError, setProfileError] = useState(false)
  const [authActionPending, setAuthActionPending] = useState(false)
  const [verificationNotice, setVerificationNotice] = useState(null)
  const authActionRef = useRef(false)

  async function fetchProfile(firebaseUser) {
    try {
      const data = await fetchMeWithHeal(firebaseUser)
      if (auth.currentUser?.uid !== firebaseUser.uid) return null
      if (data.id !== firebaseUser.uid) throw new Error('Account response did not match your sign-in. Please retry.')
      setProfile(data)
      setProfileError(false)
      return data
    } catch (err) {
      if (auth.currentUser?.uid !== firebaseUser.uid) return null
      console.error('fetchProfile failed:', err)
      setProfile(null)
      setProfileError({ status: err?.status, code: err?.code })
      return null
    }
  }

  useEffect(() => {
    if (PREVIEW) return   // preview: keep the mock user; skip the Firebase auth listener
    const unsub = onAuthStateChanged(auth, async (firebaseUser) => {
      setProfile(current => current?.id === firebaseUser?.uid ? current : null)
      setProfileError(false)
      if (firebaseUser) {
        setUser(firebaseUser)
        setLoading(false)
        // Explicit signup/login owns the profile request while it is in flight.
        // A simultaneous self-heal could overwrite the submitted name or intent.
        if (!authActionRef.current && firebaseUser.emailVerified) await fetchProfile(firebaseUser)
      } else {
        setUser(null)
        setProfile(null)
      }
      if (auth.currentUser?.uid === firebaseUser?.uid) setLoading(false)
    })
    return unsub
  }, [])

  async function signUp(email, password, { name, phone, roles = ['eater'], activeRole = 'eater', hp = '' }) {
    authActionRef.current = true
    setAuthActionPending(true)
    try {
      if (hp) throw new Error('Invalid submission')
      await getAppCheckHeaders()
      const cred = await createUserWithEmailAndPassword(auth, email, password)

      const result = await completeSignup({
        user: cred.user, profile: { name, phone, roles, activeRole, hp },
        updateName: (account, displayName) => updateFirebaseProfile(account, { displayName }),
        sync: async (account, values) => apiFetch('/api/auth/sync', await account.getIdToken(), {
          method: 'POST', body: JSON.stringify(values),
        }),
        verify: requestVerificationEmail,
        remember: (uid, values) => {
          try { sessionStorage.setItem('cc_signup_profile', JSON.stringify({ uid, profile: values })) } catch { /* unavailable storage */ }
        },
        clear: () => { try { sessionStorage.removeItem('cc_signup_profile') } catch { /* unavailable storage */ } },
      })
      // This account is still unverified. Fetch its authorized profile after
      // verification instead of blocking the inbox screen on another API call.
      setProfile(null); setProfileError(false)
      if (!result.verificationSent) {
        try { sessionStorage.setItem('cc_verification_pending', '1') } catch { /* unavailable storage */ }
      }
      return cred.user
    } finally { authActionRef.current = false; setAuthActionPending(false) }
  }

  async function login(email, password) {
    authActionRef.current = true
    setAuthActionPending(true)
    try {
      const cred = await signInWithEmailAndPassword(auth, email, password)
      if (!cred.user.emailVerified) {
        // A successful login must request mail before asking the user to check
        // their inbox. Mail failure stays recoverable in the signed-in session.
        await requestVerificationEmail(cred.user).catch(() => {})
        return { needsVerification: true }
      }

      const data = await fetchMeWithHeal(cred.user)
      if (auth.currentUser?.uid !== cred.user.uid || data.id !== cred.user.uid) throw new Error('Your signed-in account changed. Please try again.')
      setProfile(data)
      setProfileError(false)
      apiFetch('/api/auth/complete-verification', await cred.user.getIdToken(), { method: 'POST', body: '{}' }).catch(() => {})

      // Return the resolved profile so the caller routes by role off THIS value, not the async
      // `user`/`profile` state — that's what makes the post-auth destination race-free.
      return { needsVerification: false, profile: data }
    } finally { authActionRef.current = false; setAuthActionPending(false) }
  }

  async function resetPassword(email) {
    if (PREVIEW) throw new Error('Email delivery requires a connected account service.')
    await accountEmail.reset(email, lang)
  }

  async function requestVerificationEmail(account = auth.currentUser) {
    if (!account || PREVIEW) throw new Error('Sign in to request a verification email.')
    try {
      await accountEmail.verification(account, lang)
      setVerificationNotice({ uid: account.uid, requested: true })
      try { sessionStorage.removeItem('cc_verification_pending') } catch { /* storage is optional */ }
    } catch (error) {
      setVerificationNotice({ uid: account.uid, requested: false, limited: error?.status === 429 })
      throw error
    }
  }

  async function completeVerification() {
    const account = auth.currentUser
    if (!account) throw new Error('Please sign in to continue.')
    await account.reload()
    if (!account.emailVerified) throw new Error('Please verify your email first.')
    // Firebase verification authorizes the account. Optional welcome delivery
    // must not strand an already-verified customer.
    await apiFetch('/api/auth/complete-verification', await account.getIdToken(true), { method: 'POST', body: '{}' }).catch(() => {})
    const resolvedProfile = await fetchProfile(account)
    if (!resolvedProfile) throw new Error('Your email is verified. Please retry loading your account.')
    return resolvedProfile
  }

  async function logout() {
    clearPendingDestination()
    try { sessionStorage.removeItem('cookApplication') } catch { /* ignore */ }
    try { sessionStorage.removeItem('cc_signup_profile') } catch { /* ignore */ }
    // Revoke push for this device BEFORE the session dies (the PATCH clearing the
    // server-side token needs a valid bearer). Best-effort — never blocks sign-out.
    try { await revokeNotificationToken() } catch { /* ignore */ }
    await signOut(auth)
  }

  async function refreshProfile() {
    if (user) await fetchProfile(user)
  }

  async function updateProfile(updates) {
    if (!user) return
    if (PREVIEW) { setProfile(p => ({ ...p, ...updates })); return }
    const token = await user.getIdToken()
    await apiFetch('/api/auth/me', token, {
      method: 'PATCH',
      body: JSON.stringify(updates),
    })
    await fetchProfile(user)
  }

  /**
   * Flip the ACTIVE role (eater <-> cook) for accounts that already hold both
   * roles. Optimistic so the UI (BottomNav tabs, RoleRoute) switches instantly.
   * It does NOT add a role — the 'cook' role is granted only on team approval of
   * the cook application, so this is only meaningful for already-approved cooks.
   */
  async function switchRole(role) {
    setProfile((p) => (p ? { ...p, activeRole: role, active_role: role } : p))
    try {
      await updateProfile({ activeRole: role })
    } catch (err) {
      console.error('switchRole PATCH failed (keeping optimistic state):', err)
    }
  }

  // Memoized on the state the handlers close over — AuthProvider sits at the tree
  // root, and an unmemoized value object re-rendered every useAuth() consumer on
  // every provider render. Handler identities refresh exactly when user/profile do.
  const value = useMemo(() => ({
    user, profile: profile?.id === user?.uid ? profile : null, loading, profileError, authActionPending, verificationNotice,
    signUp, login, resetPassword, requestVerificationEmail, completeVerification, logout, updateProfile, switchRole, refreshProfile,
    // eslint-disable-next-line react-hooks/exhaustive-deps -- refresh handlers with state and email language
  }), [user, profile, loading, profileError, authActionPending, verificationNotice, lang])

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  )
}
