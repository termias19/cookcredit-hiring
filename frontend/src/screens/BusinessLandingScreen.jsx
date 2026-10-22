/** Hiring entry only. Links reuse existing account, application and workspace routes. */
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, ArrowUpRight, Plus, Pause, Play } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { isBusinessProfile } from '../utils/homeFor'
import { COOKCREDIT_ASSESSMENT_URL } from '../config'
import '../styles/hiring-landing.css'

const questions = [
  ['What does a hiring team see?', 'Your team can review submitted applications, CVs and recordings that applicants have agreed to share. Access is limited to the company workspace and each teammate’s permissions.'],
  ['Does CookCredit make hiring decisions?', 'No. Your team makes every hiring decision. The knife-work measurements have limitations and are not independently validated for automatic employment screening. Review the recording alongside the rest of the application.'],

]

// Decorative public footage only; never loads an applicant recording or the scorer.
function KnifeLoop() {
  const video = useRef(null)
  const [playing, setPlaying] = useState(false)
  const [failed, setFailed] = useState(false)
  const manualPause = useRef(false)
  useEffect(() => {
    const player = video.current
    const motion = window.matchMedia('(prefers-reduced-motion: reduce)')
    const connection = navigator.connection
    let visible = false
    const sync = () => {
      if (!visible || document.hidden || motion.matches || connection?.saveData || manualPause.current) {
        player.pause()
      } else {
        // Attach the source only when motion is welcome and the hero is in view.
        if (!player.getAttribute('src')) player.src = '/media/hiring-knife-loop.mp4'
        player.play().catch(() => {}) // Browsers may require the explicit play button.
      }
    }
    const observer = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; sync() })
    observer.observe(player)
    motion.addEventListener('change', sync)
    connection?.addEventListener('change', sync)
    document.addEventListener('visibilitychange', sync)
    return () => {
      observer.disconnect()
      motion.removeEventListener('change', sync)
      connection?.removeEventListener('change', sync)
      document.removeEventListener('visibilitychange', sync)
      player.pause()
    }
  }, [])
  const toggle = () => {
    const player = video.current
    manualPause.current = !player.paused
    if (!player.paused) player.pause()
    else {
      if (!player.getAttribute('src')) player.src = '/media/hiring-knife-loop.mp4'
      player.play().catch(() => {})
    }
  }
  return <figure className="hiring-film">
    <div className="hiring-film-frame">
      <video ref={video} muted loop playsInline preload="none" poster="/images/hiring-knife-poster.jpg" aria-hidden="true" onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} onError={() => { setFailed(true); setPlaying(false) }} />
      <div className="hiring-film-bottom"><span>Real knife work.<br /><em>A closer look at the craft.</em></span>{!failed && <button type="button" onClick={toggle} aria-label={playing ? 'Pause background video' : 'Play background video'}>{playing ? <Pause size={16} aria-hidden="true" /> : <Play size={16} aria-hidden="true" />}{playing ? 'Pause' : 'Play'}</button>}</div>
    </div>
    <figcaption>CookCredit assessment footage · hand and knife tracking</figcaption>
  </figure>
}

export default function BusinessLandingScreen() {
  const { user, profile } = useAuth()
  const employerPath = !user ? '/signup?next=/business/onboarding' : isBusinessProfile(profile) ? '/business/roles' : '/business/onboarding'
  const applicantPath = user ? '/applications' : '/signup?next=/applications'
  const employerLabel = isBusinessProfile(profile) ? 'Open your workspace' : 'Start hiring'
  return <div className="hiring-home">
    <a className="hiring-skip" href="#hiring-main">Skip to content</a>
    <header className="hiring-header">
      <Link className="hiring-wordmark" to="/" aria-label="CookCredit Hiring home"><img src="/cookcredit-mark-orange.svg" width="32" height="30" alt="" />CookCredit<span>Hiring</span></Link>
      <nav aria-label="Main navigation">
        <a className="hiring-nav-detail" href="#how-it-works">How it works</a>
        <a className="hiring-nav-detail" href="#for-cooks">For cooks</a>
        <Link className="hiring-signin" to={user ? '/profile' : '/login?next=/business/roles'}>{user ? 'My account' : 'Sign in'}<ArrowUpRight size={16} aria-hidden="true" /></Link>
      </nav>
    </header>
    <main id="hiring-main" tabIndex={-1}>
      <section className="hiring-intro" aria-labelledby="hiring-title">
        <div className="hiring-intro-copy">
          <p className="hiring-eyebrow">Knife skills. Seen clearly.</p>
          <h1 id="hiring-title">See the skill.<br /><em>Meet the cook.</em></h1>
          <p className="hiring-lede">Go beyond the CV with a recorded knife assessment. Watch the work, review the measurements and choose your next conversation.</p>
          <div className="hiring-actions"><Link className="hiring-button" to={employerPath}>{employerLabel}<ArrowRight size={18} aria-hidden="true" /></Link><a className="hiring-text-link" href="#for-cooks">Applying for a role?</a></div>
          {!isBusinessProfile(profile) && <p className="hiring-small">Company access is reviewed before you post your first role.</p>}
        </div>
        <KnifeLoop />
      </section>
      <section id="how-it-works" className="hiring-process" aria-labelledby="process-title">
        <div><p className="hiring-eyebrow">How it works</p><h2 id="process-title">One link.<br /><em>A better introduction.</em></h2></div>
        <ol>
          <li><span aria-hidden="true">01</span><div><h3>Share your role.</h3><p>Create a role and send applicants one link.</p></div></li>
          <li><span aria-hidden="true">02</span><div><h3>See their knife skills.</h3><p>Applicants add a CV, record the assessment and consent to sharing.</p></div></li>
          <li><span aria-hidden="true">03</span><div><h3>Review together.</h3><p>Watch recordings alongside measurements. Your team makes the decision.</p></div></li>
        </ol>
      </section>
      <section id="for-cooks" className="hiring-cooks" aria-labelledby="cooks-title">
        <div><p className="hiring-eyebrow">For cooks</p><h2 id="cooks-title">Your next kitchen<br /><em>starts here.</em></h2></div>
        <div><p>Have an invitation? Open your employer’s link to apply for the right role. You can also create your profile now.</p><Link className="hiring-button hiring-button-outline" to={applicantPath}>{user ? 'Your applications' : 'Create an applicant account'}<ArrowRight size={18} aria-hidden="true" /></Link><p className="hiring-small">Already started? <Link to={user ? '/applications' : '/login?next=/applications'}>Return to your applications</Link>.</p></div>
      </section>
      <section className="hiring-questions" aria-labelledby="questions-title">
        <div><p className="hiring-eyebrow">Your questions</p><h2 id="questions-title">Before you begin.</h2><p>Need a hand? <a href="mailto:connectwithus@cookcredit.com">Talk to us<ArrowUpRight size={15} aria-hidden="true" /></a></p></div>
        <div>{questions.map(([question, answer]) => <details key={question}><summary>{question}<Plus size={19} aria-hidden="true" /></summary><p>{answer}</p></details>)}<p className="hiring-assessment-link"><a href={COOKCREDIT_ASSESSMENT_URL} target="_blank" rel="noreferrer">Explore the practice assessment<ArrowUpRight size={16} aria-hidden="true" /><span className="hiring-sr-only"> (opens in a new tab)</span></a><span>Practice does not submit a job application.</span></p></div>
      </section>
    </main>
    <footer className="hiring-footer"><Link className="hiring-wordmark" to="/">CookCredit</Link><p>For the hands that feed us.</p><nav aria-label="Footer"><Link to="/help">Help</Link><Link to="/business/audit">Assessment limitations</Link><a href="https://cookcredit.com/privacy.html">Privacy</a><a href="https://cookcredit.com/terms.html">Terms</a></nav></footer>
  </div>
}
