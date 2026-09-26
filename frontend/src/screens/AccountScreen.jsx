import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import AccountShell from '../components/AccountShell'
import AccountDetails from '../components/AccountDetails'

export default function AccountScreen() {
  const { profile } = useAuth()
  return <AccountShell title="Your CookCredit profile" intro="Manage your account and the knife assessments you share with employers.">
    {profile && <AccountDetails key={profile.id} profile={profile}>
      <section style={{ border: '1px solid var(--cc-border)', padding: 24 }}>
        <h2 className="cc-profile-heading">Your next step</h2>
        <p style={{ color: 'var(--cc-muted)', lineHeight: 1.7, fontSize: 14 }}>Open your employer’s invitation to apply and record the correct assessment. Your submitted applications stay in your account.</p>
        <Link to="/applications" className="cc-profile-link" style={{ marginTop: 18 }}>My applications</Link>
        <p style={{ marginTop: 28, fontSize: 14 }}>Hiring cooks for your company?</p>
        <Link to="/business/onboarding" className="cc-profile-link" style={{ marginTop: 12 }}>Set up a hiring workspace</Link>
      </section>
    </AccountDetails>}
  </AccountShell>
}
