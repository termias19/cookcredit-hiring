import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { ArrowLeft, Check, ExternalLink } from 'lucide-react'
import BusinessShell from '../components/BusinessShell'
import { useBusiness } from '../context/BusinessContext'
import { useAuth } from '../context/AuthContext'
import { createBusinessBillingPortal, createBusinessCheckout, getBusinessBilling } from '../utils/Api'
import { fadeIn, staggerContainer } from '../styles/motion'

const SERIF = "var(--cc-display)"
const GREEN = '#1F6F5C'

export default function BusinessBillingScreen({ embedded = false } = {}) {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const biz = useBusiness()
  const { user } = useAuth()
  const earlyAccess = biz?.org?.integrationAccess?.earlyAccess === true
  const [billing, setBilling] = useState({ plan: biz?.org?.plan || 'trial', teamPrice: '$99' })
  const [pending, setPending] = useState('')
  const [msg, setMsg] = useState(params.get('checkout') === 'success' ? 'Checkout complete. Confirming your subscription…' : '')
  const [error, setError] = useState('')

  const refresh = useCallback(async () => {
    if (!user) return null
    const token = await user.getIdToken()
    const result = await getBusinessBilling({ token })
    setBilling(result)
    return result
  }, [user])

  useEffect(() => {
    if (biz?.loading || !biz?.org || earlyAccess) return undefined
    let live = true
    let timer
    ;(async () => {
      try {
        const result = await refresh()
        if (!live) return
        if (params.get('checkout') === 'success' && !['team', 'integration'].includes(result?.plan)) {
          let attempts = 0
          timer = window.setInterval(async () => {
            attempts += 1
            try {
              const next = await refresh()
              if (['team', 'integration'].includes(next?.plan)) { setMsg(`${next.plan === 'integration' ? 'Integration' : 'Team'} is active.`); window.clearInterval(timer) }
              else if (attempts >= 6) { setMsg('Your payment is still being confirmed. Your plan will update when confirmation arrives.'); window.clearInterval(timer) }
            } catch { window.clearInterval(timer) }
          }, 2500)
        }
      } catch (cause) { if (live) setError(cause.message || 'Billing status is unavailable.') }
    })()
    return () => { live = false; if (timer) window.clearInterval(timer) }
  }, [refresh, params, earlyAccess, biz?.loading, biz?.org])

  async function startCheckout(plan) {
    setPending(plan); setError(''); setMsg('')
    try {
      const token = await user.getIdToken()
      const requestId = globalThis.crypto?.randomUUID?.()
      if (!requestId) throw new Error('This browser cannot start a secure checkout request.')
      const result = await createBusinessCheckout({ token, requestId, plan })
      window.location.assign(result.checkoutUrl)
    } catch (cause) { setError(cause.message || 'Checkout is temporarily unavailable.'); setPending('') }
  }

  async function openPortal() {
    setPending('portal'); setError('')
    try {
      const token = await user.getIdToken()
      const result = await createBusinessBillingPortal({ token })
      window.location.assign(result.portalUrl)
    } catch (cause) { setError(cause.message || 'The billing portal is temporarily unavailable.'); setPending('') }
  }

  const plans = [
    { id: 'trial', name: 'Trial', price: 'Free', cadence: '14 days', features: ['1 admin seat', '1 open role', 'Branded application link', 'Explainable assessment evidence'] },
    { id: 'team', name: 'Team', price: billing.teamPrice || '$99', cadence: '/ month', featured: true, features: ['5 seats', 'Unlimited open roles', 'Branded link and embedded widget', 'Shortlists, evidence history, and audit export'] },
    { id: 'integration', name: 'Integration', price: billing.integrationPrice || '$299', cadence: '/ month', features: ['1,000 assessment requests / month', 'Universal API and signed webhooks', 'External job and candidate IDs', 'Branded link and embedded widget'] },
    { id: 'enterprise', name: 'Enterprise', price: 'Custom', cadence: '', features: ['Higher assessment volume', 'Discuss your access requirements', 'Implementation support', 'Contract billing'] },
  ]

  const header = <div style={{ background: '#FEFDFB', borderBottom: '1px solid #E3E0D9', padding: '20px 28px' }}>
    <button onClick={() => navigate('/business/roles')} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, background: 'none', border: 'none', cursor: 'pointer', padding: 0, marginBottom: 10 }}>
      <ArrowLeft size={14} color="#999" strokeWidth={1.5} /><span style={{ fontSize: 11, letterSpacing: 3, color: '#74756f', textTransform: 'uppercase' }}>{biz?.org?.name || 'Workspace'}</span>
    </button>
    <h1 style={{ fontFamily: SERIF, fontSize: 38, fontWeight: 500, letterSpacing: '-0.02em', color: '#1a1a1a', margin: 0 }}>Plans & billing</h1>
    <p style={{ fontSize: 13, color: '#70706b', margin: '5px 0 0' }}>{biz?.loading || !biz?.org ? 'Your workspace access and billing details.' : earlyAccess ? 'Your workspace includes five open roles. No subscription payment is required.' : 'Choose the plan that fits your hiring process. Manage payments and invoices securely with Stripe.'}</p>
  </div>

  if (biz?.loading || !biz?.org) return <BusinessShell embedded={embedded} header={embedded ? null : header} showNav={false}>
    <section style={{ padding: '32px 28px' }}>
      {biz?.loading ? <p role="status">Loading workspace access…</p> : <><p role="alert">Workspace access could not be loaded.</p><button onClick={biz?.refresh}>Retry</button></>}
    </section>
  </BusinessShell>

  if (earlyAccess) return <BusinessShell embedded={embedded} header={embedded ? null : header} showNav={false}>
    <section style={{ padding: '32px 28px', maxWidth: 720, margin: '0 auto' }}>
      <h2 style={{ fontFamily: SERIF, fontSize: 30, fontWeight: 500 }}>Free early access</h2>
      <p style={{ lineHeight: 1.8, color: '#555' }}>Use your branded assessment link, embedded widget, API and webhooks while subscription payments are being prepared.</p>
      <p style={{ lineHeight: 1.8, color: '#555' }}>{biz.org.integrationAccess.earlyAccessMonthlyLimit || 100} API assessment requests per month in each environment. Your workspace retains its existing role and seat limits.</p>
      <p style={{ lineHeight: 1.8, color: '#555' }}>No card is required and you will not be charged automatically. Subscribing later will require your choice.</p>
      <button onClick={() => navigate('/business/profile?section=integrations')} style={{ marginTop: 12, padding: '13px 22px', border: 0, background: GREEN, color: '#fff', cursor: 'pointer' }}>Open integrations</button>
    </section>
  </BusinessShell>

  return <BusinessShell embedded={embedded} header={embedded ? null : header} showNav={false}>
    <div style={{ padding: '24px 28px 40px', maxWidth: 1080, margin: '0 auto' }}>
      <AnimatePresence>{(msg || error) && <motion.p className="cc-business-notice" variants={fadeIn} initial="hidden" animate="show" exit={{ opacity: 0 }} style={{ fontSize: 13, color: error ? '#A44320' : GREEN, border: `1px solid ${error ? '#A44320' : GREEN}`, background: error ? '#FBF1EC' : '#E8F1EC', padding: '10px 12px', margin: '0 0 16px' }}>{error || msg}</motion.p>}</AnimatePresence>
      {billing.status && <p style={{ fontSize: 12, color: '#777', margin: '0 0 14px' }}>Subscription: <b>{billing.status.replaceAll('_', ' ')}</b>{billing.cancelAtPeriodEnd && billing.periodEnd ? ` · access scheduled to end ${new Date(billing.periodEnd).toLocaleDateString()}` : ''}</p>}
      {billing.integrationUsage && <div style={{ border: '1px solid #dfd5c7', background: '#fffaf2', padding: '12px 14px', marginBottom: 14, fontSize: 12, color: '#655d54' }}><b>{billing.integrationUsage.used.toLocaleString()}</b> of <b>{billing.integrationUsage.limit.toLocaleString()}</b> assessment requests used since {new Date(`${billing.integrationUsage.periodStart}T00:00:00`).toLocaleDateString()}.</div>}
      <motion.div className="cc-plan-grid" variants={staggerContainer()} initial="hidden" animate="show">
        {plans.map(plan => {
          const current = plan.id === billing.plan
          const paidSelfServe = ['team', 'integration'].includes(plan.id)
          const checkoutReady = plan.id === 'team' ? billing.checkoutConfigured : billing.integrationCheckoutConfigured
          const action = paidSelfServe && current && billing.hasCustomer ? openPortal : paidSelfServe && checkoutReady ? () => startCheckout(plan.id) : plan.id === 'enterprise' && !current ? () => { window.location.href = 'mailto:connectwithus@cookcredit.com?subject=CookCredit%20Enterprise' } : null
          const label = paidSelfServe && current && billing.hasCustomer ? 'Manage billing' : current ? 'Current plan' : paidSelfServe ? (checkoutReady ? `Choose ${plan.name}` : 'Subscriptions not open yet') : plan.id === 'enterprise' ? 'Contact sales' : 'Included fallback'
          return <motion.div className="cc-business-card" key={plan.id} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25 }} style={{ minWidth: 0, border: `1px solid ${current ? GREEN : '#E3E0D9'}`, background: '#FEFDFB', padding: '22px 20px', display: 'flex', flexDirection: 'column' }}>
            <div style={{ minHeight: 22, fontSize: 10, letterSpacing: 1.5, textTransform: 'uppercase', color: GREEN, marginBottom: 6 }}>{current ? 'Your current plan' : plan.id === 'integration' ? 'Connect your hiring software' : ''}</div>
            <div style={{ fontFamily: SERIF, fontSize: 22, fontWeight: 500, color: '#1a1a1a' }}>{plan.name}</div>
            <div style={{ margin: '6px 0 14px' }}><span style={{ fontFamily: SERIF, fontSize: 30 }}>{plan.price}</span><span style={{ fontSize: 12, color: '#74756f', marginLeft: 4 }}>{plan.cadence}</span></div>
            <ul style={{ listStyle: 'none', padding: 0, margin: '0 0 16px', flex: 1 }}>{plan.features.map(feature => <li key={feature} style={{ display: 'flex', gap: 8, alignItems: 'flex-start', fontSize: 13, color: '#555', padding: '4px 0' }}><Check size={14} color={GREEN} style={{ flexShrink: 0, marginTop: 2 }} />{feature}</li>)}</ul>
            <motion.button whileTap={action ? { scale: .97 } : undefined} onClick={action || undefined} disabled={!action || pending !== ''} style={{ width: '100%', padding: 12, fontSize: 13, fontWeight: 500, cursor: action ? 'pointer' : 'default', border: current ? '1px solid #E3E0D9' : 'none', background: action ? GREEN : '#FEFDFB', color: action ? '#fff' : '#70706b', opacity: pending ? .6 : 1, display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 6 }}>
              {pending === plan.id || (pending === 'portal' && current) ? 'Opening…' : label}{action && <ExternalLink size={13} />}
            </motion.button>
          </motion.div>
        })}
      </motion.div>
      <p style={{ fontSize: 12, color: '#70706b', marginTop: 16 }}>Paid subscriptions use Stripe for payment details, invoices, and cancellation.</p>
    </div>
  </BusinessShell>
}
