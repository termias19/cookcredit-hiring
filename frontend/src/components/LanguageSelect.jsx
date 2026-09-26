/**
 * LanguageSelect — one reusable language dropdown (replaces the 5-button strip).
 *
 * Theme-aware via `variant`: 'dark' for the landing hero, 'light' for in-app
 * surfaces (Profile, Shell). Shows native language names + a globe affordance,
 * closes on outside-click / Escape, and persists through useLang().setLang.
 */
import { useState, useRef, useEffect } from 'react'
import { Globe, Check, ChevronDown } from 'lucide-react'
import { useLang } from '../context/LangContext'
import { REGION, LANG_LABELS } from '../utils/region'

// Region-derived availability (ET has no Spanish), native names so a speaker
// recognizes their own language.
const LANGS = REGION.languages.map((code) => ({ code, label: LANG_LABELS[code] }))

export default function LanguageSelect({ variant = 'light' }) {
  const { lang, setLang } = useLang()
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    if (!open) return
    const onDoc = e => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    const onKey = e => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('mousedown', onDoc); document.removeEventListener('keydown', onKey) }
  }, [open])

  const current = LANGS.find(l => l.code === lang) || LANGS[0]
  const dark = variant === 'dark'
  const fg = dark ? '#fff' : '#1a1a1a'
  const triggerBg = dark ? 'rgba(255,255,255,0.10)' : '#fff'
  const triggerBorder = dark ? 'rgba(255,255,255,0.40)' : '#d8d8d8'
  const menuBg = dark ? '#1a1a1a' : '#fff'
  const menuBorder = dark ? 'rgba(255,255,255,0.20)' : '#e5e5e5'
  const selBg = dark ? 'rgba(255,255,255,0.12)' : '#f4f1ec'
  const hoverBg = dark ? 'rgba(255,255,255,0.08)' : '#f7f4ef'

  if (variant === 'toggle') return (
    <div role="group" aria-label={lang === 'ES' ? 'Idioma' : 'Language'} style={{ display: 'flex', maxWidth: 310 }}>
      {['EN', 'ES'].map(code => <button key={code} type="button" lang={code.toLowerCase()}
        aria-pressed={lang === code} onClick={() => setLang(code)}
        style={{ flex: 1, padding: '12px 18px', border: '1px solid #1f6f5c', cursor: 'pointer', fontSize: 14,
          background: lang === code ? '#1f6f5c' : 'transparent', color: lang === code ? '#fff' : '#1f6f5c' }}>
        {LANG_LABELS[code]}
      </button>)}
    </div>
  )

  return (
    <div ref={ref} style={{ position: 'relative', display: 'inline-block' }}>
      <button type="button" onClick={() => setOpen(o => !o)}
        aria-haspopup="listbox" aria-expanded={open} aria-label="Choose language"
        style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '7px 10px', cursor: 'pointer',
          background: triggerBg, color: fg, border: `1px solid ${triggerBorder}`, borderRadius: 6,
          fontSize: 12, fontWeight: 600, letterSpacing: 0.3 }}>
        <Globe size={14} strokeWidth={1.5} /> {current.label}
        <ChevronDown size={13} strokeWidth={1.5}
          style={{ transform: open ? 'rotate(180deg)' : 'none', transition: 'transform .15s' }} />
      </button>
      {open && (
        <ul role="listbox" style={{ position: 'absolute', right: 0, top: 'calc(100% + 6px)', minWidth: 168, zIndex: 200,
          background: menuBg, color: fg, border: `1px solid ${menuBorder}`, borderRadius: 6,
          boxShadow: '0 8px 28px rgba(0,0,0,0.18)', listStyle: 'none', margin: 0, padding: 4 }}>
          {LANGS.map(l => (
            <li key={l.code} role="option" aria-selected={l.code === lang}
              onClick={() => { setLang(l.code); setOpen(false) }}
              onMouseEnter={e => { e.currentTarget.style.background = l.code === lang ? selBg : hoverBg }}
              onMouseLeave={e => { e.currentTarget.style.background = l.code === lang ? selBg : 'transparent' }}
              style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10,
                padding: '9px 10px', cursor: 'pointer', fontSize: 13, borderRadius: 4,
                background: l.code === lang ? selBg : 'transparent' }}>
              <span>{l.label}</span>
              {l.code === lang && <Check size={14} strokeWidth={2} />}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
