import { Link } from 'react-router-dom'
import { COOKCREDIT_ASSESSMENT_URL } from '../config'

export default function CookCreditHelpScreen({ assessment = false }) {
  return <main className="cc-hiring-page" style={{ minHeight: '100svh', background: 'var(--cc-surface)', padding: '40px 22px' }}>
    <section style={{ maxWidth: 680, margin: '0 auto', lineHeight: 1.7 }}>
      <Link to="/business" style={{ color: 'var(--cc-forest)' }}>CookCredit</Link>
      <h1 style={{ fontFamily: 'var(--cc-display)', fontSize: 40, fontWeight: 400, margin: '28px 0 16px' }}>{assessment ? 'Your knife assessment' : 'Hiring through real skills'}</h1>
      <p>CookCredit helps employers review an applicant’s recorded knife work, measurements and attempt history. Companies can use an assessment link, a website widget, or the API and webhooks in their existing hiring process.</p>
      <h2 style={{ fontFamily: 'var(--cc-display)', fontSize: 27, fontWeight: 400, margin: '28px 0 10px' }}>Applying for a role</h2>
      <p>Start with the link your employer sent you. Sign in, answer the requested questions and choose whether to share your assessment. Return to your application to see its status or use an available attempt.</p>
      <p style={{ margin: '16px 0' }}><Link to="/applications" style={{ color: 'var(--cc-forest)' }}>Open my applications</Link></p>
      <h2 style={{ fontFamily: 'var(--cc-display)', fontSize: 27, fontWeight: 400, margin: '28px 0 10px' }}>Try the published assessment</h2>
      <p>The standalone assessment opens on CookCredit’s existing assessment website. Practicing there does not submit evidence to an employer.</p>
      <a href={COOKCREDIT_ASSESSMENT_URL} style={{ display: 'inline-block', padding: '12px 20px', marginTop: 18, color: '#fff', background: 'var(--cc-forest)', textDecoration: 'none' }}>Open knife assessment</a>
      <p style={{ marginTop: 30 }}>For an accommodation or a hiring decision, contact the employer that invited you. For your CookCredit account, use <Link to="/forgot">password recovery</Link> or <Link to="/profile">profile settings</Link>.</p>
      <nav style={{ display: 'flex', gap: 20, flexWrap: 'wrap', marginTop: 30, fontSize: 13 }}><a href="https://cookcredit.com/privacy.html">Privacy Policy</a><a href="https://cookcredit.com/terms.html">Terms of Use</a></nav>
    </section>
  </main>
}
