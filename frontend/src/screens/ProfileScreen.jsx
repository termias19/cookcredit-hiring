/**
 * ProfileScreen — minimal, real profile shown in the main tab bar.
 *
 * Standard Shell header (Mise eyebrow + serif "Profile"), the user's
 * name/email, a role switch (Switch to helping / Switch to getting help for dual-role
 * accounts, or a "Become a helper" CTA for client-only), and logout. Calm and
 * editorial — not a settings dump. Full helper-profile editing lands later.
 */
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { useAuth } from '../context/AuthContext'
import { useLang } from '../context/LangContext'
import Shell from '../components/Shell'
import LanguageSelect from '../components/LanguageSelect'
import { LogOut, User as UserIcon, Wrench, Home, ArrowRight, Clock, ShieldCheck, ScanLine, Pencil } from 'lucide-react'
import { REGION } from '../utils/region'
import { fadeUp, scaleIn, staggerContainer, buttonPress, hoverLift, tapScale } from '../styles/motion'

const SERIF = "'Cormorant Garamond', 'Playfair Display', Georgia, serif"

const ROLE_CHIP = {
  cook:  { label: 'Helper', bg: '#E8F1EC', color: '#1F6F5C' },
  eater: { label: 'Client', bg: '#F5F5F5', color: '#777' },
}

function Header() {
  return (
    <div style={{ background: '#FEFDFB', borderBottom: '1px solid #eee', padding: '32px 32px 20px' }}>
      <div style={{ maxWidth: 1360, margin: '0 auto' }}>
        <p style={{ fontSize: 11, letterSpacing: 3, color: '#aaa', textTransform: 'uppercase', margin: '0 0 6px' }}>Mise</p>
        <h1 style={{ fontFamily: SERIF, fontSize: 'clamp(28px, 4vw, 38px)', fontWeight: 400, color: '#1a1a1a', margin: 0 }}>Profile</h1>
      </div>
    </div>
  )
}

export default function ProfileScreen() {
  const navigate = useNavigate()
  const { user, profile, logout, switchRole } = useAuth()
  const { t } = useLang()

  async function handleLogout() {
    await logout()
    navigate('/')
  }

  if (!user) return null

  const activeRole = profile?.activeRole || profile?.active_role

  // Helper application status: none -> show "Become a helper"; pending -> "under
  // review" (no role switch yet); approved -> the team granted helper access.
  const cp = profile?.cookProfile
  const cookStatus = cp?.applicationStatus
    || (cp?.approved ? 'approved' : (cp?.appliedAt ? 'pending' : 'none'))

  // The helper's identity-verification credential — the ID + liveness check (SkillScreen) is the
  // moat, so it gets its own card in the helper section with the real verified score + a view/retake link.
  const knifeScore = cp?.skillScore ?? null
  const knifeVerified = !!cp?.skillVerified
  const knifeWhen = cp?.skillTestAt ? new Date(cp.skillTestAt).toLocaleDateString(REGION.dateLocale, { month: 'short', year: 'numeric' }) : null

  const chip = ROLE_CHIP[activeRole]

  // For a dual-role account, the toggle flips to the *other* role.
  const otherRole = activeRole === 'cook' ? 'eater' : 'cook'
  const switchCopy = otherRole === 'cook'
    ? { label: 'Switch to helping', icon: Wrench }
    : { label: 'Switch to getting help', icon: Home }
  const SwitchIcon = switchCopy.icon

  return (
    <Shell wide header={<Header />}>
      <motion.div variants={staggerContainer(0.06, 0.05)} initial="hidden" animate="show"
        style={{ padding: '28px 0 40px', display: 'flex', gap: 28, alignItems: 'flex-start', flexWrap: 'wrap' }}>

        {/* identity card — sticky sidebar on wide screens */}
        <motion.div variants={fadeUp} style={{
          background: '#fff', border: '1px solid #e5e5e5', padding: '28px 24px',
          flex: '1 1 280px', maxWidth: 340, textAlign: 'center', position: 'sticky', top: 28,
        }}>
          <div style={{
            width: 84, height: 84, flexShrink: 0, background: '#f0f0f0', borderRadius: '50%', margin: '0 auto 16px',
            display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden',
          }}>
            {profile?.photoUrl
              ? <img src={profile.photoUrl} alt="" width={84} height={84} loading="lazy" style={{ width: 84, height: 84, objectFit: 'cover' }} />
              : <UserIcon size={36} color="#999" strokeWidth={1.5} />}
          </div>
          <h2 style={{ fontFamily: SERIF, fontSize: 24, fontWeight: 400, color: '#1a1a1a', margin: '0 0 4px' }}>
            {profile?.name || user.displayName || 'User'}
          </h2>
          <p style={{ fontSize: 13, color: '#888', margin: '0 0 14px', overflowWrap: 'anywhere' }}>
            {user.email}
          </p>

          {chip && (
            <span style={{
              display: 'inline-block', padding: '4px 12px',
              fontSize: 11, fontWeight: 600, letterSpacing: 1, textTransform: 'uppercase',
              background: chip.bg, color: chip.color,
            }}>
              {chip.label}
            </span>
          )}
        </motion.div>

        {/* account content */}
        <div style={{ flex: '3 1 420px', minWidth: 0 }}>
        <motion.p variants={fadeUp} style={{ fontSize: 11, letterSpacing: 2, color: '#aaa', textTransform: 'uppercase', margin: '0 0 12px' }}>
          Account
        </motion.p>

        {cookStatus === 'approved' ? (
          <motion.button
            variants={fadeUp} whileHover={hoverLift} whileTap={tapScale}
            onClick={() => switchRole(otherRole)}
            style={{
              width: '100%', padding: '14px 16px', marginBottom: 12,
              background: '#fff', border: '1px solid #e5e5e5', cursor: 'pointer',
              display: 'flex', alignItems: 'center', gap: 10,
              fontSize: 14, color: '#1a1a1a', textAlign: 'left',
            }}
          >
            <SwitchIcon size={18} strokeWidth={1.5} color="#1F6F5C" />
            <span style={{ flex: 1 }}>{switchCopy.label}</span>
            <ArrowRight size={16} strokeWidth={1.5} color="#999" />
          </motion.button>
        ) : cookStatus === 'pending' ? (
          <motion.div variants={scaleIn} style={{
            width: '100%', padding: '14px 16px', marginBottom: 12,
            background: '#FBF3E2', border: '1px solid #C9A227',
            display: 'flex', alignItems: 'center', gap: 12 }}>
            <Clock size={20} strokeWidth={1.5} color="#B87800" style={{ flexShrink: 0 }} />
            <div>
              <p style={{ fontSize: 14, fontWeight: 600, color: '#1a1a1a', margin: '0 0 2px' }}>
                Helper application — under review
              </p>
              <p style={{ fontSize: 12, color: '#B87800', margin: 0, lineHeight: 1.5 }}>
                We&rsquo;re reviewing your bio and identity verification. We&rsquo;ll email you when you&rsquo;re
                approved — then you can switch to helping here.
              </p>
            </div>
          </motion.div>
        ) : cookStatus === 'none' ? (
          <motion.button
            variants={fadeUp} onClick={() => navigate('/onboarding/bio')} {...buttonPress}
            style={{
              width: '100%', padding: '14px 16px', marginBottom: 12,
              background: '#1F6F5C', border: 'none', cursor: 'pointer',
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
              fontSize: 14, color: '#fff', fontWeight: 600, letterSpacing: 1, textTransform: 'uppercase',
            }}
          >
            <Wrench size={16} strokeWidth={1.5} /> Become a helper
          </motion.button>
        ) : null}

        {/* edit helper profile — the Qwick/Indeed-style profile editor (bio, specialties, rate, area…) */}
        {cookStatus !== 'none' && (
          <motion.button
            variants={fadeUp} whileHover={hoverLift} whileTap={tapScale}
            onClick={() => navigate('/cook/profile/edit')}
            style={{
              width: '100%', padding: '14px 16px', marginBottom: 12,
              background: '#fff', border: '1px solid #e5e5e5', cursor: 'pointer',
              display: 'flex', alignItems: 'center', gap: 10,
              fontSize: 14, color: '#1a1a1a', textAlign: 'left',
            }}
          >
            <Pencil size={17} strokeWidth={1.5} color="#1a1a1a" />
            <span style={{ flex: 1 }}>Edit helper profile</span>
            <ArrowRight size={16} strokeWidth={1.5} color="#999" />
          </motion.button>
        )}

        {/* identity-verification credential — links the ID + liveness check (SkillScreen) into the helper section */}
        {cookStatus !== 'none' && (
          <motion.div variants={scaleIn} style={{ background: '#fff', border: '1px solid #e5e5e5', padding: 16, marginBottom: 12 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <ShieldCheck size={22} strokeWidth={1.75} color={knifeScore != null && knifeVerified ? '#1F6F5C' : '#bbb'} style={{ flexShrink: 0 }} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <p style={{ fontSize: 11, letterSpacing: 1.5, color: '#aaa', textTransform: 'uppercase', margin: '0 0 3px' }}>Identity verification</p>
                {knifeScore != null ? (
                  <p style={{ fontSize: 13, color: '#1a1a1a', margin: 0 }}>
                    <span style={{ fontFamily: SERIF, fontSize: 22, color: '#1a1a1a' }}>{knifeScore}</span>
                    <span style={{ fontSize: 12, color: '#999' }}>{' / 100 · '}{knifeVerified ? 'Verified' : 'Scored'}{knifeWhen ? ` · ${knifeWhen}` : ''}</span>
                  </p>
                ) : (
                  <p style={{ fontSize: 13, color: '#777', margin: 0, lineHeight: 1.5 }}>Complete identity verification to earn your verified score.</p>
                )}
              </div>
            </div>
            <motion.button onClick={() => navigate('/skill')} {...buttonPress} style={{
              width: '100%', marginTop: 14, padding: '12px 16px', cursor: 'pointer',
              background: knifeScore != null ? '#fff' : '#1a1a1a',
              border: knifeScore != null ? '1px solid #1a1a1a' : 'none',
              color: knifeScore != null ? '#1a1a1a' : '#fff',
              display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 8,
              fontSize: 14, fontWeight: 500, letterSpacing: 0.5 }}>
              <ScanLine size={16} strokeWidth={1.5} /> {knifeScore != null ? 'View / retake verification' : 'Complete identity verification'}
            </motion.button>
          </motion.div>
        )}

        {/* language */}
        <motion.div variants={fadeUp} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '14px 0', borderTop: '1px solid #f0f0f0', marginTop: 4, marginBottom: 4 }}>
          <span style={{ fontSize: 14, color: '#1a1a1a' }}>{t?.language || 'Language'}</span>
          <LanguageSelect variant="light" />
        </motion.div>

        {/* legal & help */}
        <motion.div variants={fadeUp} style={{ display: 'flex', flexWrap: 'wrap', gap: 16, padding: '12px 0 16px', borderTop: '1px solid #f0f0f0' }}>
          {[['about', t?.about || 'About'], ['privacy', t?.privacy || 'Privacy'], ['terms', t?.terms || 'Terms'],
            ['biometric', t?.biometric || 'Biometric'], ['help', t?.help || 'Help']].map(([path, label]) => (
            <motion.button key={path} whileTap={tapScale} onClick={() => navigate(`/${path}`)}
              style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer', fontSize: 13, color: '#777', textDecoration: 'underline' }}>
              {label}
            </motion.button>
          ))}
        </motion.div>

        {/* logout */}
        <motion.button
          variants={fadeUp} whileHover={hoverLift} whileTap={tapScale}
          onClick={handleLogout}
          style={{
            width: '100%', padding: '14px', background: 'none',
            border: '1px solid #e5e5e5', cursor: 'pointer',
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
            fontSize: 14, color: '#666',
          }}
        >
          <LogOut size={16} strokeWidth={1.5} />
          {t?.logout || 'Log out'}
        </motion.button>
        </div>
      </motion.div>
    </Shell>
  )
}
