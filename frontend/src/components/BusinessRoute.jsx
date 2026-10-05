/**
 * BusinessRoute — gates the professional B2B workspace. Requires a logged-in user with the
 * 'business' role; a logged-in user without it is sent to org onboarding (not stranded), where
 * the role is granted. Wraps children in the BusinessProvider store. Public marketing
 * (/business) and the public candidate demo stay outside this guard.
 */
import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import ProtectedRoute from './ProtectedRoute'
import { BusinessProvider } from '../context/BusinessContext'
import HiringAccessRequestScreen from '../screens/HiringAccessRequestScreen'

function BusinessAccess({ children }) {
  const { user, profile, loading } = useAuth()
  const location = useLocation()

  // OPT-IN dev bypass for standalone UI work — default OFF and never ships. Set
  // VITE_BUSINESS_DEV_BYPASS=1 in .env.local to exercise the workspace without a backend.
  // (We do NOT key this on import.meta.env.DEV — that is true for every `npm run dev`, which would
  // hide every production guard bug during development and let any dev session skip the gate.)
  if (import.meta.env.DEV && import.meta.env.VITE_BUSINESS_DEV_BYPASS === '1') return <BusinessProvider>{children}</BusinessProvider>

  if (loading) return null
  if (!user) return <Navigate to="/login" state={{ from: location }} replace />
  if (!user.emailVerified) return <Navigate to="/verify" state={{ from: location }} replace />
  if (!profile || profile.id !== user.uid || profile.employerAccessAllowed !== true) {
    return <HiringAccessRequestScreen />
  }

  // Authorization is the SERVER-resolved role only — never a client localStorage flag (which any
  // user could set in DevTools to load the candidate roster + biometric video panel). The backend
  // is the real defense (every /api/business/* read re-checks the 'business' role + org scope);
  // this guard just keeps non-business users out of the workspace UI.
  const isBusiness = (profile?.roles || []).includes('business')
  if (!isBusiness && location.pathname !== '/business/onboarding') {
    return <Navigate to="/business/onboarding" state={{ from: location }} replace />
  }
  if (isBusiness && location.pathname === '/business/onboarding') {
    return <Navigate to="/business/roles" replace />
  }
  return <BusinessProvider key={user.uid}>{children}</BusinessProvider>
}

export default function BusinessRoute({ children }) {
  return <ProtectedRoute><BusinessAccess>{children}</BusinessAccess></ProtectedRoute>
}
