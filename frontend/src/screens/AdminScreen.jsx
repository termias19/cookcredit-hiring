/**
 * AdminScreen — the helper-application review queue.
 *
 * Replaces the CLI-only approval. Admins (ADMIN_EMAILS allowlist; the route is
 * guarded on profile.isAdmin and every endpoint re-checks server-side) see pending
 * applications with the applicant's VERIFIED identity check, and approve or reject.
 * Approving grants the helper role on the applicant's next load.
 */
import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion as Motion, AnimatePresence } from 'framer-motion'
import { Check, X, RefreshCw } from 'lucide-react'
import Shell from '../components/Shell'
import { useAuth } from '../context/AuthContext'
import { listCookApplications, approveCook, rejectCook } from '../utils/Api'
import { fadeUp, staggerContainer, hoverLift, tapScale, buttonPress } from '../styles/motion'

const SERIF = "'Cormorant Garamond', Georgia, serif"
const GREEN = '#1F6F5C'
const TABS = ['pending', 'approved', 'rejected', 'all']
const grid = { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 20 }

function Header({ tab, setTab, onRefresh }) {
  return (
    <div style={{ background: '#FEFDFB', borderBottom: '1px solid #eee', padding: '32px 32px 20px' }}>
      <div style={{ maxWidth: 1360, margin: '0 auto' }}>
        <p style={{ fontSize: 11, letterSpacing: 3, color: '#aaa', textTransform: 'uppercase', margin: '0 0 6px' }}>Mise</p>
        <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 24, flexWrap: 'wrap', marginBottom: 16 }}>
          <div>
            <h1 style={{ fontFamily: SERIF, fontSize: 'clamp(28px, 4vw, 38px)', fontWeight: 600, color: '#1a1a1a', margin: '0 0 6px' }}>
              Helper applications
            </h1>
            <p style={{ fontSize: 13, color: '#777', margin: 0, maxWidth: 520 }}>
              Review the applicant's identity verification check, then approve or reject. Approving grants the helper role.
            </p>
          </div>
          <Motion.button onClick={onRefresh} whileHover={{ scale: 1.03 }} whileTap={tapScale} style={ghostBtn} aria-label="Refresh">
            <RefreshCw size={14} strokeWidth={1.5} style={{ verticalAlign: '-2px' }} /> Refresh
          </Motion.button>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {TABS.map(s => (
            <Motion.button key={s} onClick={() => setTab(s)} whileHover={{ scale: 1.03 }} whileTap={tapScale}
              style={{ ...tabBtn, background: tab === s ? '#1a1a1a' : '#fff', color: tab === s ? '#fff' : '#1a1a1a' }}>
              {s}
            </Motion.button>
          ))}
        </div>
      </div>
    </div>
  )
}

export default function AdminScreen() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [tab, setTab] = useState('pending')
  const [apps, setApps] = useState([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState('')          // uid currently being acted on

  const load = useCallback(async (status) => {
    setLoading(true); setErr('')
    try {
      const token = await user.getIdToken()
      const data = await listCookApplications({ token, status })
      setApps(Array.isArray(data?.applications) ? data.applications : [])
    } catch (e) {
      setErr(e?.message || 'Could not load applications.')
      setApps([])
    } finally {
      setLoading(false)
    }
  }, [user])

  useEffect(() => { if (user) load(tab) }, [user, tab, load])

  async function act(uid, action) {
    setBusy(uid); setErr('')
    try {
      const token = await user.getIdToken()
      if (action === 'approve') {
        await approveCook({ token, uid })
      } else {
        const note = window.prompt('Reason for rejection (optional, shown to no one but the team):') ?? ''
        await rejectCook({ token, uid, note })
      }
      await load(tab)
    } catch (e) {
      setErr(e?.message || `Could not ${action} — try again.`)
    } finally {
      setBusy('')
    }
  }

  return (
    <Shell wide header={<Header tab={tab} setTab={setTab} onRefresh={() => load(tab)} />}>
      <Motion.div variants={fadeUp} initial="hidden" animate="show" style={{ padding: '24px 0 40px' }}>
        {err && <p style={{ color: '#B4232A', fontSize: 13, marginBottom: 12 }}>{err}</p>}
        {loading ? (
          <div style={grid}>
            {[0, 1, 2, 3].map(i => (
              <Motion.div key={i} style={{ ...card, height: 168 }}
                animate={{ opacity: [0.5, 1, 0.5] }}
                transition={{ repeat: Infinity, duration: 1.4, delay: i * 0.15 }} />
            ))}
          </div>
        ) : apps.length === 0 ? (
          <p style={{ color: '#999', fontSize: 14 }}>No {tab === 'all' ? '' : tab} applications.</p>
        ) : (
          <Motion.div variants={staggerContainer()} initial="hidden" animate="show" style={grid}>
            <AnimatePresence>
              {apps.map(a => (
                <Motion.div key={a.userId} variants={fadeUp} initial="hidden" animate="show" exit={{ opacity: 0, x: -24, transition: { duration: 0.18 } }}
                  whileHover={hoverLift} style={card}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                    <div>
                      <div style={{ fontFamily: SERIF, fontSize: 22, color: '#1a1a1a' }}>{a.name || '—'}</div>
                      <div style={{ fontSize: 12, color: '#999' }}>{a.email}</div>
                    </div>
                    <span style={statusPill(a.applicationStatus)}>{a.applicationStatus}</span>
                  </div>

                  <div style={{ display: 'flex', gap: 18, margin: '12px 0', flexWrap: 'wrap' }}>
                    <Stat label="Identity verified" value={a.skillVerified ? `${a.skillScore ?? '—'} / 100` : 'not verified'} />
                    <Stat label="Tier" value={a.skillTier || '—'} />
                    <Stat label="Applied" value={a.appliedAt ? new Date(a.appliedAt).toLocaleDateString() : '—'} />
                  </div>

                  {a.bio && <p style={{ fontSize: 13, color: '#555', lineHeight: 1.5, margin: '0 0 8px', flex: 1 }}>{a.bio}</p>}
                  {Array.isArray(a.cuisines) && a.cuisines.length > 0 && (
                    <div style={{ fontSize: 12, color: '#777', marginBottom: 8 }}>Cuisines: {a.cuisines.join(', ')}</div>
                  )}
                  {a.reviewNote && <div style={{ fontSize: 12, color: '#B4232A', marginBottom: 8 }}>Note: {a.reviewNote}</div>}

                  {a.applicationStatus === 'pending' && (
                    <div style={{ display: 'flex', gap: 10, marginTop: 'auto', paddingTop: 10 }}>
                      <Motion.button disabled={busy === a.userId} onClick={() => act(a.userId, 'approve')}
                        {...buttonPress}
                        style={{ ...primaryBtn, opacity: busy === a.userId ? 0.6 : 1 }}>
                        <Check size={14} strokeWidth={2} style={{ verticalAlign: '-2px' }} /> Approve
                      </Motion.button>
                      <Motion.button disabled={busy === a.userId} onClick={() => act(a.userId, 'reject')}
                        {...buttonPress}
                        style={{ ...outlineBtn, opacity: busy === a.userId ? 0.6 : 1 }}>
                        <X size={14} strokeWidth={2} style={{ verticalAlign: '-2px' }} /> Reject
                      </Motion.button>
                    </div>
                  )}
                </Motion.div>
              ))}
            </AnimatePresence>
          </Motion.div>
        )}

        <Motion.button onClick={() => navigate('/')} whileHover={{ scale: 1.03 }} whileTap={tapScale} style={{ ...ghostBtn, marginTop: 24 }}>← Back</Motion.button>
      </Motion.div>
    </Shell>
  )
}

function Stat({ label, value }) {
  return (
    <div>
      <div style={{ fontSize: 10, letterSpacing: 1, textTransform: 'uppercase', color: '#aaa' }}>{label}</div>
      <div style={{ fontSize: 15, color: '#1a1a1a', marginTop: 2 }}>{value}</div>
    </div>
  )
}

const card = { border: '1px solid #e5e5e5', borderRadius: 4, padding: '18px 18px', background: '#fff',
  display: 'flex', flexDirection: 'column', height: '100%' }
const tabBtn = { padding: '7px 14px', border: '1px solid #1a1a1a', borderRadius: 0, cursor: 'pointer',
  fontSize: 12, fontWeight: 600, letterSpacing: 0.5, textTransform: 'capitalize' }
const primaryBtn = { padding: '9px 16px', border: 'none', borderRadius: 0, cursor: 'pointer',
  background: GREEN, color: '#fff', fontSize: 13, fontWeight: 600 }
const outlineBtn = { padding: '9px 16px', border: '1px solid #B4232A', borderRadius: 0, cursor: 'pointer',
  background: '#fff', color: '#B4232A', fontSize: 13, fontWeight: 600 }
const ghostBtn = { padding: '8px 12px', border: '1px solid #e5e5e5', borderRadius: 0, cursor: 'pointer',
  background: '#fff', color: '#555', fontSize: 12, fontWeight: 600 }

function statusPill(status) {
  const map = {
    pending: { bg: '#FFF4E5', fg: '#8A5A00' },
    approved: { bg: '#E8F1EC', fg: GREEN },
    rejected: { bg: '#FBE9EA', fg: '#B4232A' },
    none: { bg: '#f0f0f0', fg: '#999' },
  }
  const c = map[status] || map.none
  return { background: c.bg, color: c.fg, fontSize: 11, fontWeight: 600, letterSpacing: 0.5,
    textTransform: 'uppercase', padding: '4px 10px', borderRadius: 999 }
}
