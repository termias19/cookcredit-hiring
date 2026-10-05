/**
 * Roles dashboard (B2B) — every open/draft posting for the org, the entry to each Role workspace.
 * Two actions only: open a role, or post a role. Pipeline counts come from the BusinessContext store.
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Plus, ChevronRight } from 'lucide-react'
import BusinessShell from '../components/BusinessShell'
import { useBusiness } from '../context/BusinessContext'
import { fadeUp, staggerContainer, tapScale, buttonPress } from '../styles/motion'

const SERIF = "var(--cc-display)"
const GREEN = 'var(--cc-forest)'
const tabStyle = active => ({ padding: '9px 14px', border: '1px solid var(--cc-forest)', background: active ? GREEN : 'transparent', color: active ? '#fff' : GREEN, borderRadius: 2, cursor: 'pointer', fontFamily: 'inherit' })

export default function BusinessRolesScreen() {
  const navigate = useNavigate()
  const biz = useBusiness()
  const [showTrash, setShowTrash] = useState(false)

  const header = (
    <div style={{ background: 'var(--cc-surface)', borderBottom: '1px solid var(--cc-border)', padding: '20px 28px' }}>
      <span style={{ fontSize: 10, letterSpacing: 2.3, color: 'var(--cc-muted)', textTransform: 'uppercase', fontWeight: 500 }}>{biz?.org?.name || 'CookCredit business'}</span>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginTop: 4 }}>
        <h1 style={{ fontFamily: SERIF, fontSize: 38, fontWeight: 500, letterSpacing: '-0.02em', color: 'var(--cc-ink)', margin: 0 }}>Roles</h1>
        <motion.button {...buttonPress} onClick={() => navigate('/business/role/new')} style={{ display: 'inline-flex', alignItems: 'center', gap: 6,
          background: GREEN, color: '#fff', border: 'none', borderRadius: 2, padding: '10px 15px', fontSize: 13, fontWeight: 700, cursor: 'pointer' }}>
          <Plus size={15} strokeWidth={1.5} /> Post a role
        </motion.button>
      </div>
    </div>
  )

  const roles = (biz?.roles || []).filter(role => (role.status === 'trashed') === showTrash)

  return (
    <BusinessShell header={header} showNav={false}>
      <div style={{ padding: '24px 28px 36px' }}>
        <div style={{ display: 'flex', gap: 12, marginBottom: 18 }}><button style={tabStyle(!showTrash)} aria-pressed={!showTrash} onClick={() => setShowTrash(false)}>Current roles</button><button style={tabStyle(showTrash)} aria-pressed={showTrash} onClick={() => setShowTrash(true)}>Trash</button></div>
        {roles.length > 0 && (
          <motion.div variants={staggerContainer()} initial="hidden" animate="show"
            style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(min(100%, 260px), 1fr))', gap: 14 }}>
            {roles.map(r => (
              <motion.button className="cc-business-card" key={r.id} variants={fadeUp} whileHover={{ borderColor: '#b2bdb6' }} whileTap={tapScale}
                onClick={() => navigate(`/business/role/${r.id}`)} style={{ display: 'flex', flexDirection: 'column', gap: 10,
                width: '100%', textAlign: 'left', background: 'var(--cc-surface)', border: '1px solid var(--cc-border)', padding: 20, cursor: 'pointer' }}>
                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 8 }}>
                  <div style={{ fontFamily: SERIF, fontSize: 20, fontWeight: 500, color: 'var(--cc-ink)', lineHeight: 1.25 }}>{r.title}</div>
                  <ChevronRight size={16} color="#ccc" strokeWidth={1.5} style={{ flexShrink: 0, marginTop: 4 }} />
                </div>
                <div style={{ fontSize: 11, letterSpacing: 1, textTransform: 'uppercase', color: r.status === 'open' ? GREEN : '#aaa' }}>{r.status}</div>
              </motion.button>
            ))}
          </motion.div>
        )}
        {biz?.loading && !roles.length && <p style={{ color: '#74756f', fontSize: 13, padding: '20px 0', textAlign: 'center' }}>Loading roles…</p>}
        {!biz?.loading && biz?.error && !roles.length && (
          <div style={{ padding: '20px 0' }}>
            <p style={{ color: '#777', fontSize: 13, margin: '0 0 12px' }}>Couldn&rsquo;t load your roles — check your connection.</p>
            <button onClick={() => biz?.refresh?.()} style={{
              background: 'var(--cc-ink)', color: '#fff', border: 'none', padding: '10px 20px',
              fontSize: 12, fontWeight: 600, letterSpacing: 1, textTransform: 'uppercase', cursor: 'pointer',
            }}>Retry</button>
          </div>
        )}
        {!biz?.loading && !biz?.error && !roles.length && <p style={{ color: '#74756f', fontSize: 13, padding: '20px 0' }}>{showTrash ? 'Trash is empty.' : 'No roles yet. Post a role, copy its application link, then review the applicants here.'}</p>}
      </div>
    </BusinessShell>
  )
}
