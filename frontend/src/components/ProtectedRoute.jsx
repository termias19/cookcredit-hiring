/**
 * ProtectedRoute — redirects to /login if unauthenticated.
 *
 * When the user IS signed in (and email-verified) but their profile fetch
 * failed, show a retry screen instead of rendering the app with a null
 * profile — otherwise a cook/business account silently degrades to a plain
 * eater with no explanation. Unverified users skip this gate: their profile
 * fetch can legitimately 403 until they verify, and /verify handles them.
 */
import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import CookCreditBrand from './CookCreditBrand'
import { profileFailure } from '../utils/profileFailure'

function ProfileLoadError({ error, onRetry, onSignOut }) {
  const failure = profileFailure(error)
  return (
    <div style={{
      minHeight: '100svh', display: 'flex', flexDirection: 'column', alignItems: 'center',
      justifyContent: 'center', gap: 12, padding: 40, textAlign: 'center', background: '#FEFDFB',
    }}>
      <CookCreditBrand />
      <p role="alert" style={{ fontFamily: "'Cormorant Garamond', Georgia, serif", fontSize: 24, color: '#1a1a1a', margin: 0 }}>
        {failure.title}
      </p>
      <p style={{ fontSize: 14, color: '#777', margin: 0, maxWidth: 340, lineHeight: 1.5 }}>
        {failure.message}
      </p>
      <div style={{ display: 'flex', gap: 10, marginTop: 8, flexWrap: 'wrap', justifyContent: 'center' }}>
        {failure.retry && <button onClick={onRetry} style={{
          padding: '12px 32px', background: '#1a1a1a', color: '#fff',
          border: 'none', fontSize: 13, fontWeight: 600, letterSpacing: 1,
          textTransform: 'uppercase', cursor: 'pointer',
        }}>
          Retry
        </button>}
        <button onClick={onSignOut} style={{
          padding: '12px 24px', background: 'transparent', color: '#1a1a1a',
          border: '1px solid #1a1a1a', fontSize: 13, fontWeight: 600, letterSpacing: 1,
          textTransform: 'uppercase', cursor: 'pointer',
        }}>
          Sign out
        </button>
      </div>
    </div>
  )
}

export default function ProtectedRoute({ children, requireVerified = true }) {
  const { user, profile, loading, profileError, refreshProfile, logout } = useAuth()
  const location = useLocation()

  if (loading) return null

  if (!user) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  if (requireVerified && !user.emailVerified) {
    return <Navigate to="/verify" state={{ from: location }} replace />
  }

  if (!profile && profileError && user.emailVerified) {
    return <ProfileLoadError error={profileError} onRetry={() => refreshProfile()} onSignOut={() => logout()} />
  }

  if (requireVerified && user.emailVerified && !profile) {
    return <main className="cc-hiring-page" role="status" style={{ padding: 32 }}>Loading your account…</main>
  }

  return children
}
