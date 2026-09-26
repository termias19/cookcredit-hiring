import { createElement, useEffect, useMemo, useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, Check, Clipboard, Code2, Link2, RotateCcw, Webhook } from 'lucide-react'
import BusinessShell from '../components/BusinessShell'
import { useAuth } from '../context/AuthContext'
import { useBusiness } from '../context/BusinessContext'
import {
  createPartnerApiKey, createPartnerWebhook, getPartnerApiKeys, getPartnerWebhooks,
  getPartnerWebhookDeliveries, replayPartnerWebhookDelivery, revokePartnerApiKey,
  setPartnerWebhookActive, updateBusinessIntegrations, uploadCompanyLogo, removeCompanyLogo,
} from '../utils/Api'
import { BASE } from '../utils/http'

const SERIF = "var(--cc-display)"
const GREEN = '#1F6F5C'
const field = { width: '100%', border: '1px solid #E3E0D9', background: '#fff', padding: '11px 12px', borderRadius: 2, fontSize: 14, fontFamily: 'inherit', color: '#1a1a1a' }
const overline = { fontSize: 10, letterSpacing: 2, textTransform: 'uppercase', color: '#70706b', fontWeight: 500, margin: '0 0 8px' }
const panel = { border: '1px solid #E3E0D9', borderRadius: 2, background: '#FEFDFB', padding: 20 }
const darkButton = { border: 0, borderRadius: 2, background: '#1F6F5C', color: '#fff', fontWeight: 500, cursor: 'pointer' }

export default function BusinessIntegrationsScreen() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const biz = useBusiness()
  const [logoUrl, setLogoUrl] = useState('')
  const [color, setColor] = useState(GREEN)
  const [origins, setOrigins] = useState('')
  const [selectedRole, setSelectedRole] = useState('')
  const [embedKey, setEmbedKey] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [copied, setCopied] = useState('')
  const [apiKeys, setApiKeys] = useState([])
  const [webhooks, setWebhooks] = useState([])
  const [deliveries, setDeliveries] = useState([])
  const [keyName, setKeyName] = useState('Production ATS')
  const [keyEnvironment, setKeyEnvironment] = useState('live')
  const [webhookUrl, setWebhookUrl] = useState('')
  const [webhookEnvironment, setWebhookEnvironment] = useState('live')
  const [issuedSecret, setIssuedSecret] = useState(null)
  const [method, setMethod] = useState('link')
  const logoInput = useRef(null)
  const initializedOrg = useRef(null)
  const [logoBusy, setLogoBusy] = useState(false)
  const canManage = biz?.seatRole === 'admin' || biz?.org?.seatRole === 'admin'
  const access = biz?.org?.integrationAccess
  const canUseApi = access?.api ?? ['integration', 'enterprise'].includes(biz?.org?.plan)
  const canUseWidget = access?.widget ?? ['team', 'integration', 'enterprise'].includes(biz?.org?.plan)

  useEffect(() => {
    const org = biz?.org
    if (!org || initializedOrg.current === org.id) return
    initializedOrg.current = org.id
    setLogoUrl(org.branding?.logoUrl || '')
    setColor(org.branding?.color || GREEN)
    setOrigins((org.embed?.allowedOrigins || []).join('\n'))
    setEmbedKey(org.embed?.key || '')
  }, [biz?.org])

  useEffect(() => {
    if (!selectedRole && biz?.roles?.[0]) setSelectedRole(biz.roles[0].id)
  }, [biz?.roles, selectedRole])

  async function changeLogo(file) {
    if (file && (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type) || file.size > 2 * 1024 * 1024)) {
      setError('Choose a PNG, JPG or WebP logo smaller than 2 MB.'); return
    }
    setLogoBusy(true); setError(''); setMessage('')
    try {
      const token = await user.getIdToken()
      const result = file ? await uploadCompanyLogo({ token, file }) : await removeCompanyLogo({ token })
      setLogoUrl(result.org?.branding?.logoUrl || '')
      setMessage(file ? 'Logo saved. It now appears on your application links and widget.' : 'Company logo removed.')
      await biz.refresh()
    } catch (cause) { setError(cause.message || 'The logo could not be saved. Try again.') }
    finally { setLogoBusy(false); if (logoInput.current) logoInput.current.value = '' }
  }

  useEffect(() => {
    let live = true
    if (!user || !canUseApi || !canManage) return undefined
    ;(async () => {
      try {
        const token = await user.getIdToken()
        const [keys, hooks, deliveryResult] = await Promise.all([
          getPartnerApiKeys({ token }), getPartnerWebhooks({ token }), getPartnerWebhookDeliveries({ token }),
        ])
        if (live) { setApiKeys(keys.keys || []); setWebhooks(hooks.webhooks || []); setDeliveries(deliveryResult.deliveries || []) }
      } catch (cause) { if (live) setError(cause.message || 'API settings could not be loaded.') }
    })()
    return () => { live = false }
  }, [user, canUseApi, canManage, biz?.org?.id])

  const appOrigin = window.location.origin
  const brandedLink = selectedRole ? `${appOrigin}/apply/${selectedRole}` : ''
  const widgetCode = useMemo(() => selectedRole && embedKey
    ? `<script src="${appOrigin}/cookcredit-widget-v1.js" data-role="${selectedRole}" data-key="${embedKey}" data-api="${BASE}" data-app="${appOrigin}" async></script>`
    : '', [selectedRole, embedKey, appOrigin])

  async function save() {
    setBusy(true); setError(''); setMessage('')
    try {
      const token = await user.getIdToken()
      const result = await updateBusinessIntegrations({
        token,
        branding: { logoUrl: logoUrl.trim() || null, color, allowedOrigins: origins.split(/\r?\n|,/).map(value => value.trim()).filter(Boolean) },
      })
      setEmbedKey(result.org?.embed?.key || '')
      setMessage('Branding and website access saved.')
      biz.refresh()
    } catch (cause) { setError(cause.message || 'Integration settings could not be saved.') }
    finally { setBusy(false) }
  }

  async function copy(name, value) {
    if (!value) return
    try { await navigator.clipboard.writeText(value); setCopied(name); window.setTimeout(() => setCopied(''), 1600) }
    catch { setError('Clipboard access is unavailable. Select and copy the code manually.') }
  }

  async function createKey() {
    setBusy(true); setError('')
    try {
      const token = await user.getIdToken()
      const result = await createPartnerApiKey({ token, name: keyName, environment: keyEnvironment, scopes: ['assessments:read', 'assessments:write'] })
      setApiKeys(current => [result.key, ...current])
      setIssuedSecret({ label: 'API key', value: result.key.secret })
    } catch (cause) { setError(cause.message || 'API key could not be created.') }
    finally { setBusy(false) }
  }

  async function revokeKey(keyId) {
    try {
      const token = await user.getIdToken()
      const result = await revokePartnerApiKey({ token, keyId })
      setApiKeys(current => current.map(key => key.id === keyId ? result.key : key))
    } catch (cause) { setError(cause.message || 'API key could not be revoked.') }
  }

  async function createWebhook() {
    setBusy(true); setError('')
    try {
      const token = await user.getIdToken()
      const result = await createPartnerWebhook({
        token, url: webhookUrl, environment: webhookEnvironment,
        eventTypes: ['assessment.invited', 'assessment.started', 'assessment.processing', 'assessment.evidence_ready', 'assessment.review_completed', 'assessment.expired', 'assessment.withdrawn'],
      })
      setWebhooks(current => [result.webhook, ...current])
      setIssuedSecret({ label: 'Webhook signing secret', value: result.webhook.secret })
      setWebhookUrl('')
    } catch (cause) { setError(cause.message || 'Webhook could not be created.') }
    finally { setBusy(false) }
  }

  async function toggleWebhook(hook) {
    try {
      const token = await user.getIdToken()
      const result = await setPartnerWebhookActive({ token, webhookId: hook.id, active: !hook.active })
      setWebhooks(current => current.map(item => item.id === hook.id ? result.webhook : item))
    } catch (cause) { setError(cause.message || 'Webhook could not be updated.') }
  }

  async function replayDelivery(delivery) {
    try {
      const token = await user.getIdToken()
      const result = await replayPartnerWebhookDelivery({ token, deliveryId: delivery.id })
      setDeliveries(current => current.map(item => item.id === delivery.id ? result.delivery : item))
    } catch (cause) { setError(cause.message || 'Webhook delivery could not be replayed.') }
  }

  const header = <div style={{ background: '#FEFDFB', borderBottom: '1px solid #E3E0D9', padding: '20px 28px' }}>
    <button onClick={() => navigate('/business/roles')} style={{ border: 0, background: 'none', display: 'flex', gap: 6, alignItems: 'center', color: '#70706b', padding: 0, cursor: 'pointer', marginBottom: 10 }}><ArrowLeft size={14} /> {biz?.org?.name || 'Workspace'}</button>
    <h1 style={{ fontFamily: SERIF, fontSize: 38, fontWeight: 500, letterSpacing: '-0.02em', color: '#1a1a1a', margin: 0 }}>Integrations</h1>
    <p style={{ color: '#70706b', fontSize: 13, margin: '6px 0 0' }}>Add a knife skill assessment to your hiring process.</p>
  </div>

  return <BusinessShell header={header} showNav={false}>
    {access?.earlyAccess && <p role="status" style={{ padding: '12px 20px', margin: 0, background: '#E8F1EC', color: GREEN, fontSize: 13 }}>Included with your workspace · No subscription charge.{access.earlyAccessMonthlyLimit ? ` Up to ${access.earlyAccessMonthlyLimit} API assessment requests per month in each environment.` : ''}</p>}
    <div style={{ maxWidth: 920, margin: '0 auto', padding: '24px 28px 40px' }}>
      <div aria-label="Integration method" style={{ display: 'flex', flexWrap: 'wrap', gap: 8, borderBottom: '1px solid #E3E0D9', marginBottom: 24, paddingBottom: 16 }}>
        {[['link', 'Branded link'], ['widget', 'Embedded widget'], ['api', 'API + webhooks']].map(([id, label]) => <button key={id} aria-pressed={method === id} onClick={() => setMethod(id)} style={{ border: `1px solid ${method === id ? GREEN : '#E3E0D9'}`, background: method === id ? GREEN : '#fff', color: method === id ? '#fff' : '#555', padding: '11px 16px', fontSize: 13, cursor: 'pointer' }}>{label}</button>)}
      </div>
      <section className="cc-business-card" aria-label="Company branding" style={{ ...panel, marginBottom: 22 }}>
        <h2 style={{ fontFamily: SERIF, fontSize: 25, fontWeight: 500, margin: '0 0 4px' }}>Make it yours</h2>
        <p style={{ fontSize: 13, color: '#70706b', margin: '0 0 20px' }}>Your identity, from the application link to the assessment invitation.</p>
        <div className="cc-logo-upload-row">
          <div className="cc-company-logo-preview">{logoUrl ? <img src={logoUrl} alt={`${biz?.org?.name || 'Company'} logo`} /> : <span>{biz?.org?.name?.trim()?.charAt(0) || 'C'}</span>}</div>
          <div>
            <input ref={logoInput} type="file" aria-label="Company logo file" accept="image/png,image/jpeg,image/webp" disabled={!canManage || logoBusy} style={{ display: 'none' }} onChange={event => { const file = event.target.files?.[0]; if (file) changeLogo(file) }} />
            <button type="button" disabled={!canManage || busy || logoBusy} onClick={() => logoInput.current?.click()} style={{ ...darkButton, padding: '11px 18px' }}>{logoBusy ? 'Saving logo…' : logoUrl ? 'Replace logo' : 'Upload logo'}</button>
            {logoUrl && <button type="button" disabled={!canManage || busy || logoBusy} onClick={() => changeLogo(null)} style={{ border: 0, background: 'none', color: '#70706b', padding: '11px 16px', cursor: 'pointer' }}>Remove</button>}
            <p style={{ color: '#70706b', fontSize: 12, margin: '9px 0 0' }}>PNG, JPG or WebP · up to 2 MB. Transparent backgrounds work well.</p>
            {!canManage && <p style={{ fontSize: 12, color: '#70706b' }}>A workspace admin can update company branding.</p>}
          </div>
        </div>
        <div className="cc-brand-row">
          <div style={{ borderLeft: `3px solid ${color}`, padding: '10px 16px', alignSelf: 'center' }}><span style={overline}>APPLICANTS WILL SEE</span><div style={{ fontFamily: SERIF, fontSize: 22 }}>{biz?.org?.name || 'Your company'}</div><span style={{ fontSize: 12, color: '#70706b' }}>Knife skill assessment · powered by CookCredit</span></div>
          <label style={{ fontSize: 12, color: '#666' }}>Brand color<input type="color" disabled={!canManage} value={color} onChange={event => setColor(event.target.value.toUpperCase())} style={{ ...field, height: 43, marginTop: 6, padding: 4 }} /></label>
        </div>
        <label style={{ display: 'block', fontSize: 12, color: '#666', marginTop: 14 }}>Websites allowed to load your widget<textarea value={origins} onChange={event => setOrigins(event.target.value)} placeholder={'https://careers.company.com\nhttps://company.com'} rows={3} style={{ ...field, resize: 'vertical', marginTop: 6 }} /></label>
        <p style={{ fontSize: 12, color: '#70706b', lineHeight: 1.5, margin: '8px 0 16px' }}>Enter each website as https://company.com, without a page path. Only these websites can display your widget.</p>
        <button onClick={save} disabled={busy || logoBusy || !canManage} style={{ ...darkButton, padding: '11px 18px', opacity: busy ? .55 : 1 }}>{busy ? 'Saving…' : 'Save settings'}</button>
      </section>
      {(message || error) && <p role={error ? 'alert' : 'status'} style={{ fontSize: 13, color: error ? '#A44320' : GREEN, margin: '0 0 20px' }}>{error || message}</p>}

      {method !== 'api' && <label style={{ display: 'block', ...overline, margin: '0 0 14px' }}>Choose a role<select value={selectedRole} onChange={event => setSelectedRole(event.target.value)} style={{ ...field, marginTop: 7, textTransform: 'none', letterSpacing: 0 }}><option value="">Choose a role</option>{(biz.roles || []).map(role => <option key={role.id} value={role.id}>{role.title}</option>)}</select></label>}

      {[
        { id: 'link', icon: Link2, title: 'Branded link', text: 'Add this URL to an application, invitation, or job post.', value: brandedLink },
        { id: 'widget', icon: Code2, title: 'Embedded widget', text: 'Add this snippet to your careers page. Applicants see your branding and continue to CookCredit to sign in and record their assessment.', value: widgetCode, locked: !canUseWidget },
        { id: 'api', icon: Webhook, title: 'API + webhooks', text: 'Request assessments from your hiring software and receive completion updates. Keep your existing job and applicant IDs.', value: '', locked: !canUseApi },
      ].filter(item => item.id === method).map(item => <section className="cc-business-card" key={item.id} style={{ ...panel, marginTop: 14 }}>
        <div style={{ display: 'flex', gap: 11, alignItems: 'flex-start' }}>{createElement(item.icon, { size: 19, color: GREEN })}<div><h2 style={{ fontFamily: SERIF, fontSize: 21, fontWeight: 500, color: '#1a1a1a', margin: 0 }}>{item.title}</h2><p style={{ fontSize: 13, color: '#70706b', lineHeight: 1.55, margin: '5px 0 12px' }}>{item.text}</p></div></div>
        {item.locked ? <p style={{ fontSize: 12, color: '#9A6B16', margin: 0 }}>{item.id === 'widget' ? 'Choose Team or Integration to use the embedded widget.' : 'The Integration plan is required for API keys and signed webhooks.'}</p> : item.id === 'api' ? <p style={{ fontSize: 12, color: GREEN, margin: 0 }}>Create a key and connect your webhook below.</p> : <div style={{ display: 'flex', gap: 8, alignItems: 'stretch' }}><code style={{ flex: 1, minWidth: 0, background: '#F3F0E8', border: '1px solid #E3E0D9', padding: 11, fontSize: 11, overflowWrap: 'anywhere' }}>{item.value || 'Save settings and choose a role'}</code><button onClick={() => copy(item.id, item.value)} disabled={!item.value} aria-label={`Copy ${item.title}`} style={{ ...darkButton, padding: '0 13px' }}>{copied === item.id ? <Check size={16} /> : <Clipboard size={16} />}</button></div>}
      </section>)}

      {method === 'api' && canUseApi && canManage && <section className="cc-business-card" style={{ ...panel, marginTop: 14 }}>
        <p style={overline}>Integration credentials</p>
        <div style={{ background: '#1a1a1a', color: '#F7F4EC', borderRadius: 2, padding: 15, marginBottom: 14, overflowX: 'auto' }}><code style={{ fontSize: 11, whiteSpace: 'pre' }}>{`POST /api/partner/v1/assessment-requests\nIdempotency-Key: job-17-candidate-482\n\n{\n  "externalJobId": "job-17",\n  "jobTitle": "Prep Cook",\n  "candidateEmail": "candidate@example.com",\n  "externalCandidateId": "candidate-482",\n  "attemptLimit": 3,\n  "assessmentProfileVersion": "knife-motion-v1",\n  "assessmentCriteria": { "profileVersion": "knife-motion-v1", "minimumRhythm": 75, "minimumConsistency": 70, "minimumForm": 70 }\n}`}</code></div>
        {issuedSecret && <div style={{ border: `1px solid ${GREEN}`, background: '#E8F1EC', padding: 12, marginBottom: 14 }}><strong style={{ fontSize: 12 }}>{issuedSecret.label} — shown once</strong><div style={{ display: 'flex', gap: 8, marginTop: 8 }}><code style={{ flex: 1, overflowWrap: 'anywhere', fontSize: 11 }}>{issuedSecret.value}</code><button onClick={() => copy('secret', issuedSecret.value)} style={{ border: 0, background: '#1a1a1a', color: '#fff', padding: '6px 10px' }}>{copied === 'secret' ? <Check size={14} /> : <Clipboard size={14} />}</button></div></div>}
        <div className="cc-form-row"><input aria-label="API key name" value={keyName} onChange={event => setKeyName(event.target.value)} style={field} placeholder="API key name" /><select aria-label="API key environment" value={keyEnvironment} onChange={event => setKeyEnvironment(event.target.value)} style={field}><option value="test">Test</option><option value="live">Live</option></select><button onClick={createKey} disabled={busy || !keyName.trim()} style={{ ...darkButton, padding: '0 16px' }}>Create API key</button></div>
        <div style={{ margin: '10px 0 18px' }}>{apiKeys.map(key => <div key={key.id} style={{ display: 'flex', gap: 8, justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid #eee', fontSize: 12 }}><span><b>{key.name}</b> · {key.environment || 'live'} · {key.prefix}… · {key.revokedAt ? 'revoked' : 'active'}</span>{!key.revokedAt && <button onClick={() => revokeKey(key.id)} style={{ border: 0, background: 'none', color: '#A44320', cursor: 'pointer' }}>Revoke</button>}</div>)}</div>
        <div className="cc-form-row"><input type="url" aria-label="Webhook URL" value={webhookUrl} onChange={event => setWebhookUrl(event.target.value)} style={field} placeholder="https://ats.company.com/cookcredit-events" /><select aria-label="Webhook environment" value={webhookEnvironment} onChange={event => setWebhookEnvironment(event.target.value)} style={field}><option value="test">Test</option><option value="live">Live</option></select><button onClick={createWebhook} disabled={busy || !webhookUrl.trim()} style={{ ...darkButton, padding: '0 16px' }}>Add webhook</button></div>
        <p style={{ fontSize: 12, color: '#70706b', lineHeight: 1.5 }}>Test keys and webhooks stay separate from live hiring. Choose the same environment for both.</p>
        <div style={{ marginTop: 10 }}>{webhooks.map(hook => <div key={hook.id} style={{ display: 'flex', gap: 10, justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid #eee', fontSize: 12 }}><span><b>{hook.active ? 'Active' : 'Disabled'}</b> · {hook.environment || 'live'} · {hook.url}<br /><span style={{ color: '#888' }}>{hook.eventTypes.join(', ')} · {hook.failureCount} consecutive failures</span></span><button onClick={() => toggleWebhook(hook)} style={{ border: 0, background: 'none', color: hook.active ? '#A44320' : GREEN, cursor: 'pointer' }}>{hook.active ? 'Disable' : 'Enable'}</button></div>)}</div>
        {deliveries.length > 0 && <div style={{ marginTop: 18 }}><p style={overline}>Recent deliveries</p>{deliveries.slice(0, 20).map(delivery => <div key={delivery.id} style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) auto', gap: 10, padding: '8px 0', borderBottom: '1px solid #eee', fontSize: 11 }}><span><b>{delivery.eventType}</b> · {delivery.status} · {delivery.attempts} attempt{delivery.attempts === 1 ? '' : 's'}<br /><span style={{ color: '#8c8379' }}>{delivery.lastError || delivery.eventId}</span></span><button onClick={() => replayDelivery(delivery)} title="Replay with the same event ID" style={{ border: '1px solid #ded6cb', background: '#fff', color: '#5e584f', padding: '5px 8px', cursor: 'pointer' }}><RotateCcw size={13} /></button></div>)}</div>}
        <p style={{ fontSize: 11, color: '#74756f', lineHeight: 1.5 }}>CookCredit signs the exact JSON body with HMAC-SHA256 in <code>CookCredit-Signature</code>. Deliveries are stored before sending, retried with backoff, and share one stable event ID across retries.</p>
      </section>}
    </div>
  </BusinessShell>
}
