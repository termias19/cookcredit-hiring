import { workspaceDestination } from './utils/workspaceDestination'
import AssessmentSharingScreen from './screens/AssessmentSharingScreen'
import { useState, useEffect, lazy, Suspense, Component } from 'react'
import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { useAuth } from './context/AuthContext'
import { NotificationProvider } from './context/NotificationContext'
import { ThemeProvider } from './context/ThemeContext'
import SplashScreen from './components/SplashScreen'
import OfflineBanner from './components/OfflineBanner'
import ProtectedRoute from './components/ProtectedRoute'
import { authDestination, clearPendingDestination, isBusinessProfile } from './utils/homeFor'
import { pageVariants } from './styles/motion'

// ── Auth screens (public) ────────────────────────────────────────────────────
const SignupScreen        = lazy(() => import('./screens/SignupScreen'))
const LoginScreen         = lazy(() => import('./screens/LoginScreen'))
const AccountActionScreen = lazy(() => import('./screens/AccountActionScreen'))
const HiringAccessRequestScreen = lazy(() => import('./screens/HiringAccessRequestScreen'))
const OwnerAccessScreen = lazy(() => import('./screens/OwnerAccessScreen'))
const EmailUnsubscribeScreen = lazy(() => import('./screens/EmailUnsubscribeScreen'))
const BusinessSettingsScreen = lazy(() => import('./screens/BusinessSettingsScreen'))
const ForgotScreen        = lazy(() => import('./screens/ForgotScreen'))
const VerifyEmailScreen   = lazy(() => import('./screens/VerifyEmailScreen'))

// ── Business / B2B ───────────────────────────────────────────────────────────
import BusinessRoute from './components/BusinessRoute'
import { PREVIEW } from './config'
const BusinessLandingScreen    = lazy(() => import('./screens/BusinessLandingScreen'))
const BusinessApplicantsScreen  = lazy(() => import('./screens/BusinessApplicantsScreen'))
const BusinessCandidateScreen  = lazy(() => import('./screens/BusinessCandidateScreen'))
const BusinessOnboardingScreen = lazy(() => import('./screens/BusinessOnboardingScreen'))
const BusinessRolesScreen      = lazy(() => import('./screens/BusinessRolesScreen'))
const BusinessRoleScreen       = lazy(() => import('./screens/BusinessRoleScreen'))
const BusinessRoleNewScreen    = lazy(() => import('./screens/BusinessRoleNewScreen'))
const BusinessAuditScreen      = lazy(() => import('./screens/BusinessAuditScreen'))
const BusinessInviteAcceptScreen = lazy(() => import('./screens/BusinessInviteAcceptScreen'))
const HiringApplicationScreen  = lazy(() => import('./screens/HiringApplicationScreen'))
const HiringAssessmentReturnScreen = lazy(() => import('./screens/HiringAssessmentReturnScreen'))

// ── Shared screens ───────────────────────────────────────────────────────────
const AccountScreen = lazy(() => import('./screens/AccountScreen'))
const ApplicantHomeScreen = lazy(() => import('./screens/ApplicantHomeScreen'))
const HiringApplicationDetailScreen = lazy(() => import('./screens/HiringApplicationDetailScreen'))
const CookCreditHelpScreen = lazy(() => import('./screens/CookCreditHelpScreen'))

// ── Preview gallery (dev only: VITE_PREVIEW=1) ───────────────────────────────
const PreviewScreen       = lazy(() => import('./screens/PreviewScreen'))

const GlobalStyle = () => (
  <style>{`
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: 'Inter', 'Noto Sans Ethiopic', sans-serif; }
    input, button, textarea, select { font-family: inherit; -webkit-appearance: none; }
    ::-webkit-scrollbar { display: none; }
    * { scrollbar-width: none; }
    @keyframes spin { to { transform: rotate(360deg) } }
  `}</style>
)

function AuthRedirect({ children }) {
  const { user, profile, loading, authActionPending } = useAuth()
  const location = useLocation()
  if (authActionPending || PREVIEW) return children
  if (loading) return null
  if (user) {
    const dest = authDestination(profile, location.state?.from, user.uid)
    if (!user.emailVerified) return <Navigate to="/verify" state={{ from: dest }} replace />
    return <ProtectedRoute><Navigate to={dest} replace /></ProtectedRoute>
  }
  return children
}

function WorkspaceRedirect() {
  const { pathname, search } = useLocation()
  return <Navigate to={workspaceDestination(pathname, search)} replace />
}

function AccountEntry() {
  const { profile } = useAuth()
  return isBusinessProfile(profile) ? <Navigate to="/business/profile" replace /> : <AccountScreen />
}

function PublishedPolicy({ url }) {
  useEffect(() => { window.location.replace(url) }, [url])
  return <main className="cc-hiring-page" style={{ padding: 32 }}><a href={url}>Open CookCredit policy</a></main>
}

/** On SPA navigation, reset scroll and move focus to the route container —
 *  without this, keyboard/screen-reader focus strands on the previous page's
 *  (now unmounted) element. */
function RouteFocusReset() {
  const { pathname, search, hash } = useLocation()
  useEffect(() => {
    clearPendingDestination(`${pathname}${search}${hash}`)
    window.scrollTo(0, 0)
    const root = document.getElementById('route-focus-root')
    if (root) root.focus({ preventScroll: true })
  }, [pathname, search, hash])
  return null
}

/** Catches a screen render error (e.g. a data-less screen in preview) and shows a fallback with a
 *  way back, instead of blanking the whole app. */
class ScreenErrorBoundary extends Component {
  constructor(props) { super(props); this.state = { failed: false } }
  static getDerivedStateFromError() { return { failed: true } }
  componentDidCatch(err) { console.error('Screen render error:', err) }
  render() {
    if (this.state.failed) {
      return (
        <div style={{ minHeight: '100svh', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 10, padding: 40, textAlign: 'center', background: '#FEFDFB' }}>
          <p style={{ fontFamily: "'Cormorant Garamond', Georgia, serif", fontSize: 24, color: '#1a1a1a', margin: 0 }}>This page could not be loaded.</p>
          <p style={{ fontSize: 14, color: '#777', margin: 0 }}>Please reload the page or return to CookCredit.</p>
          <a href="/business" style={{ color: '#1F6F5C', fontWeight: 600, marginTop: 8 }}>Back to CookCredit</a>
        </div>
      )
    }
    return this.props.children
  }
}

export default function App() {
  const [splashDone, setSplashDone] = useState(false)
  const { loading } = useAuth()
  const location = useLocation()

  if (loading || !splashDone) return (
    <>
      <GlobalStyle />
      <SplashScreen onFinished={() => setSplashDone(true)} />
    </>
  )

  return (
    <ThemeProvider>
      <NotificationProvider>
        <GlobalStyle />
        <OfflineBanner />
        <RouteFocusReset />
        <ScreenErrorBoundary>
        <Suspense fallback={null}>
          {/* Whole-page crossfade keyed by pathname — a lightweight route transition
              that needs no per-screen changes (see src/styles/motion.js). */}
          <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={location.pathname}
            id="route-focus-root"
            tabIndex={-1}
            style={{ outline: 'none' }}
            variants={pageVariants}
            initial="initial"
            animate="animate"
            exit="exit"
          >
          <Routes location={location}>
            {/* Dev preview gallery (VITE_PREVIEW=1) — a click-through index of every screen. */}
            <Route path="/preview" element={PREVIEW ? <PreviewScreen /> : <Navigate to="/" replace />} />

            {/* ── Public routes ──────────────────────────────────────── */}
            <Route path="/" element={<BusinessLandingScreen />} />
            <Route path="/login" element={<AuthRedirect><LoginScreen /></AuthRedirect>} />
            <Route path="/signup" element={<AuthRedirect><SignupScreen /></AuthRedirect>} />
            <Route path="/account/action" element={<AccountActionScreen />} />
            <Route path="/email/unsubscribe" element={<EmailUnsubscribeScreen />} />
            <Route path="/request-access" element={<HiringAccessRequestScreen />} />
            <Route path="/owner/access" element={<ProtectedRoute><OwnerAccessScreen /></ProtectedRoute>} />
            <Route path="/forgot" element={<AuthRedirect><ForgotScreen /></AuthRedirect>} />
            <Route path="/verify" element={<ProtectedRoute requireVerified={false}><VerifyEmailScreen /></ProtectedRoute>} />

            <Route path="/about" element={<CookCreditHelpScreen />} />
            <Route path="/help" element={<CookCreditHelpScreen />} />
            <Route path="/assessment" element={<CookCreditHelpScreen assessment />} />
            <Route path="/privacy" element={<PublishedPolicy url="https://cookcredit.com/privacy.html" />} />
            <Route path="/terms" element={<PublishedPolicy url="https://cookcredit.com/terms.html" />} />
            <Route path="/biometric" element={<PublishedPolicy url="https://cookcredit-knife-demo.web.app/legal/biometric.html" />} />

            <Route path="/business" element={<BusinessLandingScreen />} />
            <Route path="/business/audit" element={<BusinessAuditScreen />} />
            <Route path="/resume" element={<Navigate to="/applications" replace />} />
            <Route path="/apply/:roleId" element={<HiringApplicationScreen />} />
            <Route path="/application-assessment-return/:sessionId" element={<ProtectedRoute><HiringAssessmentReturnScreen /></ProtectedRoute>} />
            <Route path="/business/invite/:token" element={<ProtectedRoute><BusinessInviteAcceptScreen /></ProtectedRoute>} />

            {/* ── Business workspace — gated to the 'business' role ───── */}
            <Route path="/business/onboarding" element={<BusinessRoute><BusinessOnboardingScreen /></BusinessRoute>} />
            <Route path="/business/dashboard" element={<Navigate to="/business/candidates" replace />} />
            <Route path="/business/profile" element={<BusinessRoute><BusinessSettingsScreen /></BusinessRoute>} />
            <Route path="/business/candidates" element={<BusinessRoute><BusinessApplicantsScreen /></BusinessRoute>} />
            <Route path="/business/candidate/:id" element={<BusinessRoute><BusinessCandidateScreen /></BusinessRoute>} />
            <Route path="/business/roles" element={<BusinessRoute><BusinessRolesScreen /></BusinessRoute>} />
            <Route path="/business/role/new" element={<BusinessRoute><BusinessRoleNewScreen /></BusinessRoute>} />
            <Route path="/business/role/:id/edit" element={<BusinessRoute><BusinessRoleNewScreen /></BusinessRoute>} />
            <Route path="/business/role/:id" element={<BusinessRoute><BusinessRoleScreen /></BusinessRoute>} />
            <Route path="/business/shortlists" element={<BusinessRoute><WorkspaceRedirect /></BusinessRoute>} />
            <Route path="/business/team" element={<BusinessRoute><WorkspaceRedirect /></BusinessRoute>} />
            <Route path="/business/billing" element={<BusinessRoute><WorkspaceRedirect /></BusinessRoute>} />
            <Route path="/business/integrations" element={<BusinessRoute><WorkspaceRedirect /></BusinessRoute>} />

            <Route path="/profile" element={<ProtectedRoute><AccountEntry /></ProtectedRoute>} />
            <Route path="/applications" element={<ProtectedRoute><ApplicantHomeScreen /></ProtectedRoute>} />
            <Route path="/application/:applicationId" element={<ProtectedRoute><HiringApplicationDetailScreen /></ProtectedRoute>} />
            <Route path="/assessment-sharing/:roleId/:attemptId" element={<ProtectedRoute><AssessmentSharingScreen /></ProtectedRoute>} />
            {/* Retired bookmarks stay inside CookCredit. No old service or ID-capture screens are imported. */}
            <Route path="/skill" element={<Navigate to="/assessment" replace />} />
            <Route path="/onboarding/bio" element={<Navigate to="/profile" replace />} />
            <Route path="/cook/profile/edit" element={<Navigate to="/profile" replace />} />
            <Route path="/dashboard" element={<Navigate to="/applications" replace />} />
            <Route path="/install" element={<Navigate to="/profile" replace />} />

            {/* ── Catch-all ──────────────────────────────────────────── */}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
          </motion.div>
          </AnimatePresence>
        </Suspense>
        </ScreenErrorBoundary>
      </NotificationProvider>
    </ThemeProvider>
  )
}
