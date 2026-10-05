import { Link } from 'react-router-dom'
import { UserCircle } from 'lucide-react'
import { PREVIEW } from '../config'
import CookCreditBrand from './CookCreditBrand'

export default function AccountShell({ title, intro, children }) {
  return <main className="cc-hiring-page" style={{ minHeight: '100svh', background: 'var(--cc-surface)', color: 'var(--cc-ink)' }}>
    <header style={{ borderBottom: '1px solid var(--cc-border)', padding: '18px clamp(18px, 4vw, 48px)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 20, flexWrap: 'wrap' }}>
      <CookCreditBrand />
      <nav aria-label="CookCredit account" style={{ display: 'flex', gap: 22, fontSize: 14, alignItems: 'center' }}>
        <Link to="/applications" style={{ color: 'var(--cc-forest)' }}>My applications</Link>
        <Link to="/profile" style={{ display: 'flex', alignItems: 'center', gap: 7, color: 'var(--cc-forest)' }}><UserCircle size={21} /> Profile</Link>
      </nav>
    </header>
    {PREVIEW && <div className="cc-preview-note" role="status">UI preview · sample account. No live application is submitted.</div>}
    <div style={{ maxWidth: 1000, margin: '0 auto', padding: '36px clamp(18px, 4vw, 36px) 48px' }}>
      <h1 style={{ fontFamily: 'var(--cc-display)', fontSize: 'clamp(32px, 5vw, 42px)', fontWeight: 400 }}>{title}</h1>
      {intro && <p style={{ margin: '12px 0 28px', color: 'var(--cc-muted)', fontSize: 14, lineHeight: 1.7 }}>{intro}</p>}
      {children}
      <nav aria-label="Policies" style={{ display: 'flex', gap: 20, marginTop: 36, flexWrap: 'wrap', fontSize: 13 }}>
        <a href="https://cookcredit.com/privacy.html" style={{ color: 'var(--cc-muted)' }}>Privacy Policy</a>
        <a href="https://cookcredit.com/terms.html" style={{ color: 'var(--cc-muted)' }}>Terms of Use</a>
        <Link to="/help" style={{ color: 'var(--cc-muted)' }}>Help</Link>
      </nav>
    </div>
  </main>
}
