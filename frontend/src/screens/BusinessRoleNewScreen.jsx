/**
 * Post-a-role (B2B) — role-first, structured required elements. Picking the role routes the form.
 * Only the ESSENTIALS show by default (role, title, pay, shifts, skills, cert, verified); the rest
 * (station, employment, experience, physical, soft) sit behind "More requirements" with smart
 * defaults already applied. Scored elements are must-have (hard gate) or preferred (soft weight),
 * capped at 5 must-haves. Pay is mandatory (pay-transparency law); physical reqs are ADA essential-
 * function framed. The ONE free-text box never enters the match. See ELITE_B2B_DESIGN.md.
 */
import { useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { ArrowLeft, Check, ChevronDown, ChevronRight, Plus, Trash2 } from 'lucide-react'
import BusinessShell from '../components/BusinessShell'
import PlaybackViewControl from '../components/PlaybackViewControl'
import MetricRange from '../components/MetricRange'
import { rolePublicationError } from '../utils/rolePublicationError'
import { useBusiness } from '../context/BusinessContext'
import { labelOf } from '../data/culinaryTaxonomy'
import {
  ROLES, EMPLOYMENT, SHIFTS, EXPERIENCE, COOK_STATIONS, PHYSICAL,
  FOOD_HANDLER_ID, MAX_MUST_HAVES, templateFor,
} from '../data/roleRequirements'
import { fadeUp, staggerContainer, buttonPress, tapScale } from '../styles/motion'

const SERIF = "var(--cc-display)"
const GREEN = '#1F6F5C', GOLD = '#9A781E'
const lbl = { display: 'block', fontSize: 10, fontWeight: 500, letterSpacing: 1.5, textTransform: 'uppercase', color: '#70706b', margin: '18px 0 6px' }
const note = { fontSize: 11, color: '#74756f', textTransform: 'none', letterSpacing: 0, marginLeft: 6 }
const input = { width: '100%', padding: '11px 12px', border: '1px solid #E3E0D9', background: '#fff', borderRadius: 2, fontSize: 15, color: '#1a1a1a', fontFamily: 'inherit' }
const seg = on => ({ border: `1px solid ${on ? GREEN : '#E3E0D9'}`, background: on ? GREEN : '#fff', color: on ? '#fff' : '#526057', borderRadius: 2, padding: '7px 11px', fontSize: 12, cursor: 'pointer' })
const QUESTION_TYPES = [
  ['short_text', 'Short answer'], ['long_text', 'Long answer'], ['yes_no', 'Yes / no'],
  ['select', 'Choose one'], ['multiselect', 'Choose several'], ['phone', 'Phone'],
]

function Pick({ items, value, onPick, multi }) {
  const on = id => multi ? value.includes(id) : value === id
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
      {items.map(it => { const id = it.id || it, text = it.label || it
        return <motion.button key={id} type="button" whileHover={{ scale: 1.05 }} whileTap={tapScale}
          animate={{ scale: on(id) ? 1.04 : 1 }} transition={{ type: 'spring', stiffness: 400, damping: 20 }}
          onClick={() => onPick(id)} style={seg(on(id))}>{text}</motion.button> })}
    </div>
  )
}

export default function BusinessRoleNewScreen() {
  const navigate = useNavigate()
  const biz = useBusiness()
  const [roleId, setRoleId] = useState('')
  const [title, setTitle] = useState('')
  const [employment, setEmployment] = useState('Full-time')
  const [shifts, setShifts] = useState([])
  const [payMin, setPayMin] = useState('')
  const [payMax, setPayMax] = useState('')
  const [tips, setTips] = useState(false)
  const [experience, setExperience] = useState('Under 1 year')
  const [station, setStation] = useState('')
  const [skillState, setSkillState] = useState({})
  const [foodHandler, setFoodHandler] = useState(false)
  const [physical, setPhysical] = useState([])
  const [soft, setSoft] = useState([])
  const [minAge, setMinAge] = useState('')
  const [thresholds, setThresholds] = useState({ minimumRhythm: 70, maximumRhythm: 100, minimumConsistency: 70, maximumConsistency: 100, minimumForm: 70, maximumForm: 100 })
  const [description, setDescription] = useState('')
  const [assessmentInstructions, setAssessmentInstructions] = useState('')
  const [locationLabel, setLocationLabel] = useState('')
  const [attemptLimit, setAttemptLimit] = useState(3)
  const [questions, setQuestions] = useState([])
  const [showMore, setShowMore] = useState(false)

  const tpl = roleId ? templateFor(roleId) : null
  const mustCount = useMemo(
    () => Object.values(skillState).filter(s => s === 'must').length + (foodHandler ? 1 : 0),
    [skillState, foodHandler])

  function cycleSkill(id) {
    setSkillState(prev => {
      const cur = prev[id]
      if (cur === 'must') { const n = { ...prev }; delete n[id]; return n }
      if (cur === 'preferred') { return mustCount >= MAX_MUST_HAVES ? prev : { ...prev, [id]: 'must' } }
      return { ...prev, [id]: 'preferred' }
    })
  }
  const toggle = (id, list, set) => set(list.includes(id) ? list.filter(x => x !== id) : [...list, id])
  const addQuestion = () => setQuestions(current => [...current, {
    id: `question_${Date.now().toString(36)}_${current.length + 1}`,
    label: '', type: 'short_text', required: false, options: [],
  }])
  const changeQuestion = (index, patch) => setQuestions(current => current.map((question, i) => i === index ? { ...question, ...patch } : question))
  const removeQuestion = index => setQuestions(current => current.filter((_, i) => i !== index))

  function pickRole(id) {
    setRoleId(id)
    setTitle(ROLES.find(r => r.id === id)?.label || '')
    setPhysical(templateFor(id).physicalDefault || [])
    setSkillState({}); setStation(''); setFoodHandler(false); setThresholds({ minimumRhythm: 70, maximumRhythm: 100, minimumConsistency: 70, maximumConsistency: 100, minimumForm: 70, maximumForm: 100 }); setMinAge(''); setShowMore(false)
  }

  const questionsValid = questions.every(question => question.label.trim() &&
    (!['select', 'multiselect'].includes(question.type) || question.options.filter(Boolean).length >= 2))
  const canPublish = roleId && title.trim() && locationLabel.trim() && payMin && payMax && questionsValid && mustCount <= MAX_MUST_HAVES &&
    (Object.values(skillState).some(s => s === 'must') || foodHandler)

  const [publishing, setPublishing] = useState(false)
  const [publishError, setPublishError] = useState('')

  async function publish() {
    if (publishing) return
    const must = Object.keys(skillState).filter(k => skillState[k] === 'must')
    const pref = Object.keys(skillState).filter(k => skillState[k] === 'preferred')
    setPublishing(true); setPublishError('')
    try {
      const r = await biz.addRole({
        title: title.trim(), status: 'open',
        role: roleId, station: station || null,
        employmentType: employment, shifts, payMin: +payMin || null, payMax: +payMax || null, tips,
        experience, minAge: minAge || null, mustHave: must, required: must, preferred: pref,
        certsRequired: foodHandler ? [FOOD_HANDLER_ID] : [],
        assessmentCriteria: { profileVersion: 'knife-motion-v1', ...thresholds },
        physical, softSkills: soft, verifiedAxis: tpl?.verifiedAxis || null,
        loc: biz?.org?.loc || null, radiusM: 50000,
        locationLabel: locationLabel.trim(), workMode: 'onsite', attemptLimit,
        applicationQuestions: questions.map(question => ({
          ...question, label: question.label.trim(),
          options: ['select', 'multiselect'].includes(question.type)
            ? question.options.map(option => option.trim()).filter(Boolean) : [],
        })),
        assessmentInstructions: assessmentInstructions.trim() || null,
        description: description.trim() || null,    // unscored — never enters match
      })
      if (r?.id) { navigate(`/business/role/${r.id}`); return }
      setPublishing(false); setPublishError(rolePublicationError())
    } catch (error) {
      setPublishing(false); setPublishError(rolePublicationError(error))
    }
  }

  const header = (
    <div style={{ background: '#FEFDFB', borderBottom: '1px solid #E3E0D9', padding: '20px 28px' }}>
      <button onClick={() => navigate('/business/roles')} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, background: 'none', border: 'none', cursor: 'pointer', padding: 0, marginBottom: 10 }}>
        <ArrowLeft size={14} color="#999" strokeWidth={1.5} />
        <span style={{ fontSize: 11, letterSpacing: 3, color: '#74756f', textTransform: 'uppercase' }}>Roles</span>
      </button>
      <h1 style={{ fontFamily: SERIF, fontSize: 32, fontWeight: 500, letterSpacing: '-0.02em', color: '#1a1a1a', margin: 0 }}>Post a role</h1>
    </div>
  )

  return (
    <BusinessShell header={header} showNav={false}>
      <motion.div initial="hidden" animate="show" variants={fadeUp} style={{ padding: '10px 28px 40px', maxWidth: 680, margin: '0 auto' }}>
        <label style={{ ...lbl, marginTop: 14 }}>Which role?</label>
        <Pick items={ROLES} value={roleId} onPick={pickRole} />

        {tpl && (
          <motion.div key={roleId} initial="hidden" animate="show" variants={staggerContainer(0.05)}>
            {/* ── essentials ── */}
            <motion.div variants={fadeUp}>
              <label style={lbl}>Title</label>
              <input value={title} onChange={e => setTitle(e.target.value)} style={input} />
            </motion.div>

            <motion.div variants={fadeUp}>
              <label style={lbl}>Work location <span style={note}>shown on the application link</span></label>
              <input value={locationLabel} onChange={e => setLocationLabel(e.target.value)} placeholder="Neighborhood, city, or venue" style={input} />
              <p style={{ fontSize: 11, color: '#74756f', margin: '6px 0 0' }}>Applicants provide a city and may add neighborhood-level coordinates. Exact home coordinates are not stored.</p>
            </motion.div>

            <motion.div variants={fadeUp}>
              <label style={lbl}>Pay range / hr <span style={note}>shown to applicants</span></label>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                <input type="number" value={payMin} onChange={e => setPayMin(e.target.value)} placeholder="min" style={{ ...input, width: 100 }} />
                <span style={{ color: '#74756f' }}>–</span>
                <input type="number" value={payMax} onChange={e => setPayMax(e.target.value)} placeholder="max" style={{ ...input, width: 100 }} />
                {tpl.tips && (
                  <div style={{ display: 'flex', gap: 6, marginLeft: 4 }}>
                    <motion.button type="button" whileTap={tapScale} onClick={() => setTips(false)} style={seg(!tips)}>No tips</motion.button>
                    <motion.button type="button" whileTap={tapScale} onClick={() => setTips(true)} style={seg(tips)}>+ Tips</motion.button>
                  </div>
                )}
              </div>
            </motion.div>

            <motion.div variants={fadeUp}>
              <label style={lbl}>Shifts <span style={note}>when you need them</span></label>
              <Pick items={SHIFTS.map(s => ({ id: s, label: s }))} value={shifts} onPick={id => toggle(id, shifts, setShifts)} multi />
            </motion.div>

            <motion.div variants={fadeUp}>
              <label style={lbl}>Skills <span style={note}>tap = preferred · tap again = must-have</span></label>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {tpl.skills.map(id => {
                  const st = skillState[id]
                  return <motion.button key={id} type="button" whileHover={{ scale: 1.05 }} whileTap={tapScale}
                    animate={{ scale: st ? 1.04 : 1 }} transition={{ type: 'spring', stiffness: 400, damping: 20 }}
                    onClick={() => cycleSkill(id)} style={{
                    border: `1px solid ${st === 'must' ? '#1a1a1a' : st === 'preferred' ? GOLD : '#e5e5e5'}`,
                    background: st === 'must' ? '#1a1a1a' : st === 'preferred' ? GOLD : '#fff',
                    color: st ? '#fff' : '#555', padding: '6px 11px', fontSize: 12, cursor: 'pointer' }}>
                    {labelOf(id)}{st === 'must' ? ' · must' : ''}</motion.button>
                })}
              </div>
            </motion.div>

            {tpl.foodHandler && (
              <motion.label variants={fadeUp} style={{ display: 'flex', alignItems: 'flex-start', gap: 8, marginTop: 16, fontSize: 13, color: '#555' }}>
                <input type="checkbox" checked={foodHandler} onChange={e => setFoodHandler(e.target.checked)} style={{ marginTop: 2, accentColor: GREEN }} />
                <span>Require a food handler card — held <b>or obtainable within 30 days of hire</b>.</span>
              </motion.label>
            )}

            <motion.div variants={fadeUp}>
              <label style={lbl}>Knife assessment criteria</label>
              {Object.entries({ Rhythm: 'Rhythm', Consistency: 'Consistency', Form: 'Form' }).map(([axis, title]) =>
                <MetricRange key={axis} title={title} minimum={thresholds[`minimum${axis}`]} maximum={thresholds[`maximum${axis}`]}
                  onChange={(minimum, maximum) => setThresholds(current => ({ ...current, [`minimum${axis}`]: minimum, [`maximum${axis}`]: maximum }))} />)}
              <label style={{ display: 'flex', gap: 8, fontSize: 13, alignItems: 'center' }}>
                <input type="checkbox" checked={thresholds.minimumCadence !== undefined} style={{ accentColor: GREEN }}
                  onChange={event => setThresholds(current => {
                    const next = { ...current }
                    if (event.target.checked) { next.minimumCadence = 0; next.maximumCadence = 30 }
                    else { delete next.minimumCadence; delete next.maximumCadence }
                    return next
                  })} /> Set an optional pace range
              </label>
              {thresholds.minimumCadence !== undefined && <MetricRange title="Pace" unit="strokes / second" limit={30} step={0.1}
                minimum={thresholds.minimumCadence} maximum={thresholds.maximumCadence}
                onChange={(minimumCadence, maximumCadence) => setThresholds(current => ({ ...current, minimumCadence, maximumCadence }))} />}
              <p style={{ fontSize: 12, color: '#70706b', lineHeight: 1.6 }}>Drag the minimum and maximum controls to set your range. Rhythm describes timing steadiness; consistency describes stroke-amplitude steadiness; form describes the tracked chopping motion. Pace is a rate, not a quality score. Review stroke count and the recording for context.</p>
              <p style={{ fontSize: 12, color: '#70706b', lineHeight: 1.6 }}>These criteria match the published knife assessment and are saved with each application. Live assessment measurements are not independently verified. Review them with the recording; hiring decisions remain yours.</p>
            </motion.div>

            <motion.div variants={fadeUp}>
              <div style={{ marginBottom: 18 }}><p style={{ fontSize: 12 }}>Your recording view (does not change applicant requirements)</p><PlaybackViewControl /></div>
                <label style={lbl}>Assessment attempts <span style={note}>completed tries; history stays visible</span></label>
              <Pick items={[1, 2, 3].map(value => ({ id: value, label: `${value} ${value === 1 ? 'try' : 'tries'}` }))} value={attemptLimit} onPick={setAttemptLimit} />
            </motion.div>

            {/* ── more requirements (collapsed; defaults already applied) ── */}
            <motion.button variants={fadeUp} type="button" whileTap={tapScale} onClick={() => setShowMore(s => !s)} style={{
              display: 'inline-flex', alignItems: 'center', gap: 6, background: 'none', border: 'none',
              cursor: 'pointer', padding: 0, marginTop: 22, fontSize: 13, color: GREEN }}>
              {showMore ? <ChevronDown size={15} strokeWidth={1.5} /> : <ChevronRight size={15} strokeWidth={1.5} />}
              {showMore ? 'Fewer requirements' : 'More requirements'}
              <span style={{ color: '#74756f', fontSize: 12 }}>· employment, experience{tpl.station ? ', station' : ''}, physical, soft skills</span>
            </motion.button>

            <AnimatePresence initial={false}>
              {showMore && (
                <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}
                  transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }} style={{ overflow: 'hidden' }}>
                {tpl.station && (<><label style={lbl}>Station</label>
                  <Pick items={COOK_STATIONS.map(s => ({ id: s, label: s }))} value={station} onPick={setStation} /></>)}

                <label style={lbl}>Employment</label>
                <Pick items={EMPLOYMENT.map(e => ({ id: e, label: e }))} value={employment} onPick={setEmployment} />

                <label style={lbl}>Experience <span style={note}>a range, not a cutoff</span></label>
                <Pick items={EXPERIENCE.map(e => ({ id: e, label: e }))} value={experience} onPick={setExperience} />

                {tpl.alcohol && (<p style={{ fontSize: 12, color: '#74756f', marginTop: 14 }}>
                  Alcohol-server cert is keyed to your location (TABC, RBS, MAST…) and accepted “within N days of hire” — set at publish.</p>)}

                {tpl.minAge && (<><label style={lbl}>Minimum age <span style={note}>for alcohol service</span></label>
                  <Pick items={[{ id: '18+', label: '18+' }, { id: '21+', label: '21+' }]} value={minAge} onPick={setMinAge} /></>)}

                <label style={lbl}>Physical requirements <span style={note}>essential functions</span></label>
                <Pick items={PHYSICAL} value={physical} onPick={id => toggle(id, physical, setPhysical)} multi />
                <p style={{ fontSize: 11, color: '#74756f', marginTop: 6 }}>Shown as essential functions “with or without reasonable accommodation,” with an accommodation path — never a silent auto-reject.</p>

                {tpl.soft && (<><label style={lbl}>Soft skills <span style={note}>preferred</span></label>
                  <Pick items={tpl.soft.map(id => ({ id, label: labelOf(id) }))} value={soft} onPick={id => toggle(id, soft, setSoft)} multi /></>)}
                </motion.div>
              )}
            </AnimatePresence>

            <p style={{ fontSize: 11, color: mustCount > MAX_MUST_HAVES ? '#C4561F' : '#aaa', margin: '18px 0 0' }}>
              {mustCount} / {MAX_MUST_HAVES} must-haves — keep hard requirements few; other skills can be preferred.
            </p>

            <motion.div variants={fadeUp}>
              <label htmlFor="assessment-instructions" style={lbl}>Assessment instructions <span style={note}>optional · shown before recording</span></label>
              <textarea id="assessment-instructions" value={assessmentInstructions} onChange={e => setAssessmentInstructions(e.target.value)} maxLength={1500} rows={3}
                placeholder="Keep your knife hand, blade and cutting board in view. Record 20–60 seconds at your normal, safe pace. Review, then submit."
                style={{ ...input, resize: 'vertical', lineHeight: 1.5 }} />
              <p style={{ fontSize: 12, color: '#70706b', margin: '6px 0 0' }}>Leave blank to use CookCredit’s instructions. Your company logo comes from Integrations.</p>
            </motion.div>

            <motion.div variants={fadeUp}>
              <label style={lbl}>About this role <span style={note}>optional · shown to candidates · doesn’t affect matching</span></label>
              <textarea value={description} onChange={e => setDescription(e.target.value)} rows={3}
                placeholder="Culture, team, what a shift looks like…" style={{ ...input, resize: 'vertical', lineHeight: 1.5 }} />
            </motion.div>

            <motion.div variants={fadeUp}>
              <div style={{ display: 'flex', alignItems: 'end', justifyContent: 'space-between', gap: 12 }}>
                <label style={lbl}>Application questions <span style={note}>optional · up to 20</span></label>
                <button type="button" onClick={addQuestion} disabled={questions.length >= 20} style={{ border: 0, background: 'none', color: GREEN, padding: '0 0 6px', cursor: 'pointer', display: 'flex', gap: 5, alignItems: 'center', fontSize: 12 }}><Plus size={14} /> Add question</button>
              </div>
              <div style={{ display: 'grid', gap: 10 }}>
                {questions.map((question, index) => <div className="cc-business-card" key={question.id} style={{ border: '1px solid #E3E0D9', borderRadius: 2, padding: 13, background: '#FEFDFB' }}>
                  <div className="cc-question-row">
                    <input value={question.label} onChange={event => changeQuestion(index, { label: event.target.value })} placeholder="Question" style={input} />
                    <select value={question.type} onChange={event => changeQuestion(index, { type: event.target.value, options: [] })} style={input}>
                      {QUESTION_TYPES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                    </select>
                    <button type="button" aria-label="Remove question" onClick={() => removeQuestion(index)} style={{ border: 0, background: 'none', color: '#74756f', cursor: 'pointer', padding: 7 }}><Trash2 size={16} /></button>
                  </div>
                  {['select', 'multiselect'].includes(question.type) && <input value={question.options.join(', ')} onChange={event => changeQuestion(index, { options: event.target.value.split(',') })} placeholder="Options, separated by commas" style={{ ...input, marginTop: 8 }} />}
                  <label style={{ display: 'flex', alignItems: 'center', gap: 7, marginTop: 9, fontSize: 12, color: '#666' }}><input type="checkbox" checked={question.required} onChange={event => changeQuestion(index, { required: event.target.checked })} style={{ accentColor: GREEN }} /> Required</label>
                </div>)}
                {!questions.length && <p style={{ margin: 0, fontSize: 12, color: '#74756f' }}>No extra questions. CookCredit still collects the applicant’s city, consent, and assessment attempts.</p>}
              </div>
            </motion.div>

            <motion.div variants={fadeUp}>
              <motion.button {...buttonPress} onClick={publish} disabled={!canPublish || publishing} style={{ width: '100%', marginTop: 20, padding: 14, border: 'none',
                background: GREEN, color: '#fff', borderRadius: 2, fontSize: 14, fontWeight: 500, letterSpacing: 0.2,
                opacity: (canPublish && !publishing) ? 1 : 0.45, cursor: (canPublish && !publishing) ? 'pointer' : 'not-allowed',
                display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
                <Check size={16} strokeWidth={2} /> {publishing ? 'Publishing…' : 'Publish role'}
              </motion.button>
              {publishError && <p role="alert" style={{ fontSize: 12, color: '#C4561F', margin: '10px 0 0', textAlign: 'center' }}>{publishError}</p>}
            </motion.div>
          </motion.div>
        )}
      </motion.div>
    </BusinessShell>
  )
}
