/**
 * Identity verification -- the ID + liveness verification gate.
 *
 * Flow: intro -> ID capture (environment-facing camera, still photo of a
 * government ID) -> liveness capture (user-facing camera + MediaPipe
 * FaceLandmarker guides the applicant to turn their head and blink, while a
 * short clip records) -> STOP -> submit the ID photo + liveness trajectory
 * (+clip) to the backend, which verifies it SERVER-SIDE (/api/skills/submit)
 * -> result (verified/disputed/insufficient).
 *
 * This screen only captures the ID photo + face trajectory and shows the
 * verdict; the authoritative verification is computed on the server.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { Check, Camera, RotateCcw } from 'lucide-react'
import { FilesetResolver, FaceLandmarker } from '@mediapipe/tasks-vision'
import Shell from '../components/Shell'
import InfoModal from '../components/InfoModal'
import { PrivacyContent, TermsContent, BiometricContent } from '../components/InfoPages'
import { useAuth } from '../context/AuthContext'
import { useLang } from '../context/LangContext'
import { submitSkillTest, getSkillStatus, getSkillUploadUrl, putToSignedUrl, submitCookApplication, getSkillAttempt } from '../utils/Api'
import { fadeUp, scaleIn, staggerContainer, buttonPress, tapScale, EASE } from '../styles/motion'

const SERIF = "'Cormorant Garamond', 'Playfair Display', Georgia, serif"
const GREEN = '#1F6F5C', GOLD = '#C9A227', GOLD_TEXT = '#B87800', ERROR = '#D32F2F'
const WASM = 'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm'
const FACE_MODEL = 'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task'
// MediaPipe FaceMesh (468-point) landmark indices used for the two liveness
// signals: an eye-aspect-ratio (EAR) blink detector, and a nose/cheek
// asymmetry ratio used as a coarse head-turn detector.
const EYE_L = { upper: 159, lower: 145, left: 33, right: 133 }
const EYE_R = { upper: 386, lower: 374, left: 362, right: 263 }
const NOSE = 1, CHEEK_L = 234, CHEEK_R = 454
const EAR_CLOSED = 0.19, EAR_OPEN = 0.24            // hysteresis band for a "blink"
const TURN_RATIO_LO = 0.38, TURN_RATIO_HI = 0.62    // nose/cheek ratio band for "turned"
const COUNTDOWN = 3, MIN_SEC = 12, MAX_SEC = 60
// Freeze watchdog: if the capture loop produces no frame for this long (camera /
// MediaPipe stalled), warn the user and shut the capture off automatically instead
// of leaving a dead, frozen screen.
const FREEZE_SEC = 6
// Overall guard on the submit chain (record blob -> upload -> POST -> verify) so the
// 'submitting' phase can never freeze on "verifying…" if a step hangs.
const SUBMIT_TIMEOUT_MS = 30000

// Biometric consent (BIPA-style). The capture screen shows only the compact line; the full
// release is the "Biometric notice" link (BiometricContent in the InfoModal). We log WHAT the
// user saw + that they affirmed it + WHEN as the record of consent. `hash` is the sha256 of
// `text` computed at build time (not in-browser), tying the record to byte-identical text.
// The IL/TX/WA state gate and an append-only consent log are the SERVER's responsibility.
const CONSENT_DOC = {
  id: 'biometric-notice', version: '2026-07-30',
  hash: 'sha256:2b1ec748312ffb52bbb887d278c5109ae5c977394f940fd469c7618756951911',
  text: "I agree to capture a photo of my government-issued ID and a short video of my face " +
        "(biometric) to verify my identity, deleted when that's done or 3 years after I last use Mise. " +
        "Biometric notice",
}

function buildConsentRecord({ bio, age }) {
  // This screen is the helper-VALIDATION gate, so training is opted-OUT by default — the user
  // still grants the release, but the tiered default governs use (Biometric Notice §3).
  return {
    consent_type: 'biometric_release', consent_given: true,
    doc_id: CONSENT_DOC.id, doc_version: CONSENT_DOC.version, doc_hash: CONSENT_DOC.hash,
    on_screen_text: CONSENT_DOC.text,
    biometric_notice_ref: 'inapp:BiometricContent#v' + CONSENT_DOC.version,
    affirmations: { data_and_biometric: !!bio, age_18_plus: !!age },
    training_opt_in: false, training_default_applied: 'VALIDATION_default_out',
    session_tier: 'validation',
    consent_timestamp: new Date().toISOString(),
    locale: (typeof navigator !== 'undefined' && navigator.language) || 'en-US',
    region: { country: null, subdivision: null, source: 'unverified-client' },
    state_gate_passed: null,                 // SERVER must enforce IL/TX/WA gate + set this
    user_agent: (typeof navigator !== 'undefined' && navigator.userAgent) || '',
    consent_method: 'electronic_signature_checkbox', schema_version: '1.0',
  }
}

// Eye-aspect-ratio: vertical eyelid gap / horizontal eye width. Drops sharply
// when the eye closes; a close->open round trip across the hysteresis band
// below counts as one blink.
function eyeAspectRatio(upper, lower, left, right) {
  const vert = Math.hypot(upper.x - lower.x, upper.y - lower.y)
  const horiz = Math.hypot(left.x - right.x, left.y - right.y) || 1
  return vert / horiz
}

function Header() {
  return (
    <div style={{ background: '#FEFDFB', borderBottom: '1px solid #eee', padding: '18px 20px 14px' }}>
      <p style={{ fontSize: 11, letterSpacing: 3, color: '#aaa', textTransform: 'uppercase', margin: '0 0 4px' }}>Mise</p>
      <h1 style={{ fontFamily: SERIF, fontSize: 28, fontWeight: 400, color: '#1a1a1a', margin: 0 }}>Identity verification</h1>
    </div>
  )
}

export default function SkillScreen() {
  const navigate = useNavigate()
  const location = useLocation()
  const { t } = useLang()
  const { user, profile, refreshProfile } = useAuth()
  const isCook = (profile?.roles || []).includes('cook')
  // If we arrived from the become-a-helper flow, an application draft is carried
  // here (router state, with a sessionStorage fallback for refreshes). The
  // stored draft is honored only for the user who created it (no cross-user leak).
  const application = useMemo(() => {
    if (location.state?.application) return location.state.application
    try {
      const draft = JSON.parse(sessionStorage.getItem('cookApplication') || 'null')
      if (draft && (!draft.uid || draft.uid === user?.uid)) return draft
    } catch { /* ignore */ }
    return null
  }, [location.state, user?.uid])
  // An already-approved helper taking the check is RETESTING, not applying.
  const applying = !!application && !isCook
  const [applied, setApplied] = useState(false)
  const [phase, setPhase] = useState('intro')          // intro|capturing|submitting|result|error
  const [captureStep, setCaptureStep] = useState('id')  // 'id' (ID photo) | 'liveness' (face check)
  const [idPhoto, setIdPhoto] = useState(null)          // { dataUrl, base64 } — captured ID still
  const [blinkCount, setBlinkCount] = useState(0)
  const [elapsed, setElapsed] = useState(0)
  const [count, setCount] = useState(COUNTDOWN)
  const [result, setResult] = useState(null)
  const [err, setErr] = useState('')
  const [prev, setPrev] = useState(null)
  const [committing, setCommitting] = useState(false)   // uploading + posting the chosen attempt
  const [committed, setCommitted] = useState(false)     // a (non-application) attempt was submitted
  const [attempt, setAttempt] = useState(null)          // server SkillAttempt view (verification state)
  const [verifying, setVerifying] = useState(false)     // recompute in flight (PROVISIONAL/VERIFYING -> polling)
  const [agreedBio, setAgreedBio] = useState(false)     // biometric release — default OFF (separate, affirmative)
  const [agreed18, setAgreed18] = useState(false)        // 18+ attestation
  const [infoModal, setInfoModal] = useState(null)       // 'terms' | 'privacy' | 'biometric' | null

  const videoRef = useRef(null)
  const canvasRef = useRef(null)
  const S = useRef({})
  const phaseRef = useRef(phase)
  useEffect(() => { phaseRef.current = phase }, [phase])
  // The captured-but-not-yet-submitted attempt: { trajectory, frameIdx, durationSec, blob, idPhoto }.
  // Retakes overwrite/clear it; nothing here is uploaded until the applicant commits.
  const pendingRef = useRef(null)
  // Client-generated idempotency key for the committed attempt (new per capture) + the
  // verification poll timer (so a retake / unmount cancels an in-flight poll).
  const sessionIdRef = useRef(null)
  const pollRef = useRef(null)
  const okRef = useRef(false)   // did the on-device read succeed? (drives auto-submit on stop)

  useEffect(() => {
    let live = true
    ;(async () => {
      try {
        if (!user) return
        const tok = await user.getIdToken()
        const s = await getSkillStatus(tok)
        if (live) setPrev(s)
      } catch { /* ignore */ }
    })()
    return () => { live = false; teardown() }
  }, [user])

  function teardown() {
    const s = S.current
    if (pollRef.current) { clearTimeout(pollRef.current); pollRef.current = null }
    if (s.raf) cancelAnimationFrame(s.raf)
    if (s.watchdog) clearInterval(s.watchdog)
    if (s.recorder && s.recorder.state !== 'inactive') { try { s.recorder.stop() } catch { /* already stopped */ } }
    if (s.stream) s.stream.getTracks().forEach(tr => tr.stop())
    if (s.idStream) s.idStream.getTracks().forEach(tr => tr.stop())
    if (s.landmarker) { try { s.landmarker.close() } catch { /* already closed */ } }
    S.current = {}
  }

  // Runs on its own 1s timer (independent of the requestAnimationFrame loop, which
  // is what freezes). If no frame has been processed for FREEZE_SEC, the capture has
  // stalled -> warn + shut off. Also a hard wall-clock cap at MAX_SEC as a backstop.
  function watchdog() {
    const s = S.current
    if (phaseRef.current !== 'capturing') return
    const now = performance.now()
    const sinceFrame = (now - (s.lastTick || s.startedAt)) / 1000
    const el = (now - s.startedAt) / 1000
    if (sinceFrame > FREEZE_SEC) {
      setErr(`Capture froze — no camera frames for ${Math.round(sinceFrame)}s. Stopped automatically; please retake.`)
      setPhase('error')
      teardown()
      return
    }
    if (el >= MAX_SEC) stop()
  }

  // Step 1: environment-facing camera, still photo of a government ID.
  async function startId() {
    if (!agreedBio || !agreed18) { setErr('Please confirm the consent boxes to begin.'); return }
    setErr(''); setResult(null); setIdPhoto(null); setBlinkCount(0); setElapsed(0); setCount(COUNTDOWN)
    setCommitted(false); setAttempt(null); setVerifying(false); pendingRef.current = null   // fresh take discards any uncommitted attempt
    sessionIdRef.current = _uuid()                                          // idempotency key for THIS take
    if (pollRef.current) { clearTimeout(pollRef.current); pollRef.current = null }
    let stream
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false,
      })
    } catch {
      setErr('Camera blocked. Allow camera access (Chrome/Safari over https) and retry.'); setPhase('error'); return
    }
    S.current = { idStream: stream }
    setCaptureStep('id')
    setPhase('capturing')
    // The <video> only mounts once React renders the 'capturing'+'id' branch — wait a
    // frame so the ref attaches before we touch it, same as the liveness step below.
    await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))
    const video = videoRef.current
    if (!video) { stream.getTracks().forEach(tr => tr.stop()); setErr('Camera view failed to start. Retry.'); setPhase('error'); return }
    try {
      video.srcObject = stream
      await new Promise(r => (video.onloadedmetadata = r))
      await video.play()
    } catch {
      stream.getTracks().forEach(tr => tr.stop())
      setErr('Could not start the camera preview. Retry.'); setPhase('error'); return
    }
  }

  // Snap the current video frame as the ID photo, release the environment camera, and
  // hold the still (dataURL + base64) for the review step / eventual submit.
  function captureIdPhoto() {
    const video = videoRef.current
    if (!video || !video.videoWidth) return
    const c = document.createElement('canvas')
    c.width = video.videoWidth; c.height = video.videoHeight
    c.getContext('2d').drawImage(video, 0, 0, c.width, c.height)
    const dataUrl = c.toDataURL('image/jpeg', 0.85)
    setIdPhoto({ dataUrl, base64: dataUrl.split(',')[1] || '' })
    const s = S.current
    if (s.idStream) { s.idStream.getTracks().forEach(tr => tr.stop()); s.idStream = null }
  }

  function retakeId() {
    setIdPhoto(null)
    startId()
  }

  // Step 2: user-facing camera + MediaPipe FaceLandmarker. Guides the applicant to turn
  // their head and blink while a short clip records; the geometric signals below are an
  // on-device (provisional) liveness read — the server re-verifies from the video.
  async function startLiveness() {
    setCaptureStep('liveness')
    setElapsed(0); setCount(COUNTDOWN); setBlinkCount(0)
    const s = (S.current = {
      trajectory: [], chunks: [], turnedLeft: false, turnedRight: false, eyeClosed: false, blinks: 0,
      framesTotal: 0, framesWithFace: 0, startedAt: 0, lastProc: 0, frameIdx: 0,
    })
    try {
      s.stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: 'user' }, width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false,
      })
    } catch {
      setErr('Camera blocked. Allow camera access (Chrome/Safari over https) and retry.'); setPhase('error'); return
    }
    // The <video>/<canvas> swap to the liveness branch only once captureStep flips —
    // wait a frame so React attaches the refs before srcObject= is set.
    await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))
    const video = videoRef.current
    if (!video) { teardown(); setErr('Camera view failed to start. Retry.'); setPhase('error'); return }
    try {
      video.srcObject = s.stream
      await new Promise(r => (video.onloadedmetadata = r))
      await video.play()
      resizeCanvas()
    } catch {
      setErr('Could not start the camera preview. Retry.'); teardown(); setPhase('error'); return
    }
    try {
      const fileset = await FilesetResolver.forVisionTasks(WASM)
      const makeLandmarker = (delegate) => FaceLandmarker.createFromOptions(fileset, {
        baseOptions: { modelAssetPath: FACE_MODEL, delegate },
        runningMode: 'VIDEO', numFaces: 1,
        minFaceDetectionConfidence: 0.5, minFacePresenceConfidence: 0.5, minTrackingConfidence: 0.5,
      })
      // GPU is MUCH faster than CPU for smooth, low-latency face tracking. Try GPU
      // first; fall back to CPU only if GPU init fails.
      try { s.landmarker = await makeLandmarker('GPU') }
      catch { s.landmarker = await makeLandmarker('CPU') }
    } catch {
      setErr('Face model failed to load. Check your connection and retry.'); teardown(); setPhase('error'); return
    }
    try {
      let mime = ''
      for (const m of ['video/webm;codecs=vp9', 'video/webm;codecs=vp8', 'video/webm', 'video/mp4'])
        if (window.MediaRecorder && MediaRecorder.isTypeSupported(m)) { mime = m; break }
      s.recorder = new MediaRecorder(s.stream, { videoBitsPerSecond: 2500000, ...(mime && { mimeType: mime }) })
      s.recorder.ondataavailable = (ev) => { if (ev.data && ev.data.size) s.chunks.push(ev.data) }
      s.recorder.start(1000)
    } catch { s.recorder = null }
    s.startedAt = performance.now()
    s.lastTick = s.startedAt
    s.detCanvas = document.createElement('canvas')
    s.detCtx = s.detCanvas.getContext('2d', { willReadFrequently: true })
    setPhase('capturing')
    s.watchdog = setInterval(watchdog, 1000)
    s.raf = requestAnimationFrame(loop)
  }

  function resizeCanvas() {
    const v = videoRef.current, c = canvasRef.current
    if (v && c && v.videoWidth) { c.width = v.videoWidth; c.height = v.videoHeight }
  }

  function loop() {
    const s = S.current
    if (phaseRef.current !== 'capturing') return
    const now = performance.now()
    if (videoRef.current && videoRef.current.readyState >= 2 && now - s.lastProc >= 1000 / 30) {
      s.lastProc = now
      try { processFrame(now) } catch { /* keep looping */ }
    }
    s.raf = requestAnimationFrame(loop)
  }

  function processFrame(now) {
    const s = S.current
    s.lastTick = now              // heartbeat for the freeze watchdog
    const tSec = (now - s.startedAt) / 1000
    s.frameIdx += 1
    // Throttle the React UI state (elapsed/countdown text) to ~6fps. It drives only the
    // "Xs" label, the countdown, and the MIN_SEC button gate — none need per-frame updates.
    if (now - (s.lastUi || 0) >= 160) {
      s.lastUi = now
      setElapsed(tSec)
      if (tSec < COUNTDOWN) setCount(Math.ceil(COUNTDOWN - tSec))
    }
    const video = videoRef.current, canvas = canvasRef.current
    if (!video.videoWidth) return
    if (canvas.width !== video.videoWidth) resizeCanvas()

    const vw = video.videoWidth, vh = video.videoHeight
    const dw = 384, dh = Math.max(1, Math.round(dw * vh / vw))   // smaller = faster MediaPipe inference = fresher overlay
    if (s.detCanvas.width !== dw) { s.detCanvas.width = dw; s.detCanvas.height = dh }
    s.detCtx.drawImage(video, 0, 0, dw, dh)
    let res
    try { res = s.landmarker.detectForVideo(s.detCanvas, Math.round(now)) } catch { return }

    const faces = res.faceLandmarks || []
    const lm = faces[0] || null
    const past = tSec >= COUNTDOWN
    const W = canvas.width, H = canvas.height

    if (past) {
      s.framesTotal += 1
      if (lm) {
        s.framesWithFace += 1
        const P = i => ({ x: lm[i].x * W, y: lm[i].y * H })
        const ear = (eyeAspectRatio(P(EYE_L.upper), P(EYE_L.lower), P(EYE_L.left), P(EYE_L.right)) +
                     eyeAspectRatio(P(EYE_R.upper), P(EYE_R.lower), P(EYE_R.left), P(EYE_R.right))) / 2
        if (!s.eyeClosed && ear < EAR_CLOSED) {
          s.eyeClosed = true
        } else if (s.eyeClosed && ear > EAR_OPEN) {
          s.eyeClosed = false
          s.blinks += 1
          setBlinkCount(s.blinks)
          s.trajectory.push({ t: +tSec.toFixed(3), type: 'blink', ear: +ear.toFixed(3) })
        }
        const nose = P(NOSE), cheekL = P(CHEEK_L), cheekR = P(CHEEK_R)
        const dL = Math.hypot(nose.x - cheekL.x, nose.y - cheekL.y)
        const dR = Math.hypot(nose.x - cheekR.x, nose.y - cheekR.y)
        const ratio = dL / (dL + dR || 1)
        if (ratio < TURN_RATIO_LO && !s.turnedLeft) {
          s.turnedLeft = true
          s.trajectory.push({ t: +tSec.toFixed(3), type: 'turn', dir: 'left', ratio: +ratio.toFixed(3) })
        }
        if (ratio > TURN_RATIO_HI && !s.turnedRight) {
          s.turnedRight = true
          s.trajectory.push({ t: +tSec.toFixed(3), type: 'turn', dir: 'right', ratio: +ratio.toFixed(3) })
        }
      }
    }
    drawOverlay(lm)
    if (tSec >= MAX_SEC) stop()
  }

  function drawOverlay(lm) {
    const c = canvasRef.current
    if (!c) return
    const ctx = c.getContext('2d'), W = c.width, H = c.height
    ctx.clearRect(0, 0, W, H)
    if (!lm) return
    const P = i => ({ x: lm[i].x * W, y: lm[i].y * H })
    // Faint dot markers on the landmarks the liveness check reads, so the applicant can
    // see tracking is live (mirrors the earlier hand-skeleton overlay for the knife test).
    ctx.fillStyle = 'rgba(43,217,184,0.85)'
    for (const i of [NOSE, CHEEK_L, CHEEK_R, EYE_L.upper, EYE_L.lower, EYE_L.left, EYE_L.right,
      EYE_R.upper, EYE_R.lower, EYE_R.left, EYE_R.right]) {
      const p = P(i)
      ctx.beginPath(); ctx.arc(p.x, p.y, 3, 0, Math.PI * 2); ctx.fill()
    }
  }

  async function stop() {
    const s = S.current
    if (phaseRef.current !== 'capturing') return
    // Stop the render loop + watchdog synchronously (neither can hang).
    if (s.raf) cancelAnimationFrame(s.raf)
    if (s.watchdog) clearInterval(s.watchdog)
    // Show the on-device result IMMEDIATELY: a pure computation from data we already
    // have, touching no camera / model / network. The applicant always sees their
    // check the instant capture ends.
    const faceDetectedPct = s.framesTotal ? Math.round(100 * s.framesWithFace / s.framesTotal) : 0
    const turned = !!(s.turnedLeft && s.turnedRight)
    const blinks = s.blinks || 0
    const ok = turned && blinks >= 2 && faceDetectedPct >= 50
    setResult({ ok, turned, blinks, faceDetectedPct })
    setPhase('result')
    // Auto-submit: a readable take is uploaded + verified by the server WITHOUT a second
    // tap (the missing step that left earlier attempts unscored). RETAKE still cancels it.
    okRef.current = ok
    if (okRef.current) setCommitting(true)
    // Stash this attempt for a POSSIBLE explicit submit. Nothing is uploaded yet:
    // retakes are free (on-device read only); only the attempt the applicant commits is
    // sent to the server + stored — one video per applicant, no orphaned retake clips.
    pendingRef.current = { trajectory: s.trajectory, frameIdx: s.frameIdx, durationSec: elapsed, blob: null, idPhoto }
    // Finalize the clip + release camera/model in the background (time-boxed) so a
    // hang can't freeze the result; hold the blob locally for a possible submit.
    const snap = { recorder: s.recorder, chunks: s.chunks, stream: s.stream, landmarker: s.landmarker }
    S.current = { done: true }            // release refs so the unmount teardown is a no-op
    setTimeout(() => finalizeClip(snap), 0)
  }

  // Build the clip + release the camera/model. Runs AFTER the result is on screen and
  // does NOT upload — it just holds the blob on pendingRef in case the applicant submits.
  async function finalizeClip(snap) {
    let blob = null
    try {
      if (snap.recorder && snap.recorder.state !== 'inactive') {
        blob = await new Promise(res => {
          const finish = () => res(snap.chunks.length ? new Blob(snap.chunks, { type: snap.recorder.mimeType || 'video/webm' }) : null)
          const to = setTimeout(finish, 4000)          // don't hang if onstop never fires
          snap.recorder.onstop = () => { clearTimeout(to); finish() }
          try { snap.recorder.stop() } catch { clearTimeout(to); res(null) }
        })
      }
    } catch { blob = null }
    try { if (snap.stream) snap.stream.getTracks().forEach(tr => tr.stop()) } catch { /* ignore */ }
    try { if (snap.landmarker) snap.landmarker.close() } catch { /* ignore */ }
    if (pendingRef.current) pendingRef.current.blob = blob
    // The clip is ready — auto-submit for server (GPU) verification. commitSubmission is
    // idempotent on session_id and no-ops if there's nothing to send / already committing done.
    if (okRef.current && pendingRef.current && !committed && !applied) commitSubmission()
  }

  // Explicit submit of the chosen attempt: upload the clip + post the ID photo + face
  // trajectory for server-side verification + review. Time-boxed so it can't hang. For
  // applying helpers it also files the helper application. Retakes never reach here, so
  // nothing throwaway is ever uploaded or stored.
  async function commitSubmission() {
    const p = pendingRef.current
    if (!p) { setErr('Nothing to submit — retake.'); return }
    setCommitting(true); setErr('')
    try {
      const token = await user.getIdToken()
      const work = (async () => {
        // Reuse an already-successful upload on retry (p.videoUrl survives a failed
        // submit), and name the object by session_id server-side — together these
        // make the upload idempotent per capture: no duplicate blobs.
        let videoUrl = p.videoUrl || null
        if (!videoUrl && p.blob && p.blob.size) {
          try {
            const ct = (p.blob.type || '').includes('mp4') ? 'video/mp4' : 'video/webm'
            const { upload_url, video_url } = await getSkillUploadUrl({ token, contentType: ct, sessionId: sessionIdRef.current })
            await putToSignedUrl(upload_url, p.blob, ct)
            videoUrl = video_url
            p.videoUrl = video_url
          } catch { videoUrl = null }   // -> multipart fallback
        }
        // The on-device (provisional, client-claimed) liveness read — recomputed + reconciled
        // against the video server-side. session_id makes upload+recompute idempotent.
        const od = result ? { turned: result.turned, blinks: result.blinks, faceDetectedPct: result.faceDetectedPct } : {}
        const payload = {
          metadata: { schema: 'identity-verification-0.1', verification_type: 'id_liveness',
            duration_sec: +p.durationSec.toFixed(1), frames: p.frameIdx, ts: new Date().toISOString(),
            consent: buildConsentRecord({ bio: agreedBio, age: agreed18 }),
            ...(p.idPhoto?.base64 && { id_photo_base64: p.idPhoto.base64 }) },
          trajectory: p.trajectory,
          session_id: sessionIdRef.current,
          on_device: od,
          ...(videoUrl && { video_url: videoUrl }),
        }
        return submitSkillTest({ token, payload, videoBlob: videoUrl ? null : p.blob })
      })()
      const timeout = new Promise((_, rej) =>
        setTimeout(() => rej(new Error('Submit timed out — check your connection and try again.')), SUBMIT_TIMEOUT_MS))
      const resp = await Promise.race([work, timeout])
      if (resp && typeof resp === 'object') {
        setAttempt(resp)                                            // provisional attempt view + verification state
        const terminal = TERMINAL_STATES.includes(resp.verificationState)
        if (resp.attempt_id && !terminal) { setVerifying(true); pollAttempt(resp.attempt_id) }
      }
      // Applying to be a helper? File the application in the same step.
      if (applying && application) {
        await submitCookApplication({ token, application })
        try { sessionStorage.removeItem('cookApplication') } catch { /* ignore */ }
        try { await refreshProfile() } catch { /* profile refreshes on next load */ }
        setApplied(true)
      } else {
        setCommitted(true)
      }
      pendingRef.current = null
    } catch (e) {
      setErr(e.message || 'Submit failed — try again.')
    } finally {
      setCommitting(false)
    }
  }

  // Phase 2: poll the attempt until the authoritative video recompute lands
  // (VERIFIED | DISPUTED | INSUFFICIENT) or we give up after ~3 min. Self-cancels
  // on retake/unmount via pollRef. The credential is stamped server-side on VERIFIED.
  async function pollAttempt(attemptId, tries = 0) {
    const MAX_TRIES = 40           // ~40 * 5s ≈ 3.3 min
    try {
      const token = await user.getIdToken()
      const a = await getSkillAttempt({ token, id: attemptId })
      if (a && a.verificationState) {
        setAttempt(a)
        if (TERMINAL_STATES.includes(a.verificationState)) { setVerifying(false); return }
      }
    } catch { /* transient — keep polling */ }
    if (tries >= MAX_TRIES) { setVerifying(false); return }
    pollRef.current = setTimeout(() => pollAttempt(attemptId, tries + 1), 5000)
  }

  return (
    <Shell header={<Header />} showNav={!applying}>
      <div style={{ padding: '24px 20px', maxWidth: 520, margin: '0 auto' }}>
      <AnimatePresence mode="wait">

        {phase === 'intro' && (
          <motion.div key="intro" variants={staggerContainer(0.06)} initial="hidden" animate="show"
            exit={{ opacity: 0, transition: { duration: 0.18 } }}>
            <motion.p variants={fadeUp} style={{ fontSize: 14, color: '#555', lineHeight: 1.5 }}>
              Two quick steps: first, a clear photo of a government ID; then a short
              face check where we&rsquo;ll ask you to turn your head and blink, so we can
              confirm it&rsquo;s really you. We verify your identity to list you as a helper.
            </motion.p>
            {prev?.tested && (
              <p style={{ fontSize: 13, color: '#777', margin: '10px 0' }}>
                Current: {prev.verified ? 'verified' : 'not yet verified'} — you can retake.
              </p>
            )}
            {/* Why the last take didn't verify — without this, a DISPUTED user who left
                the page saw only "not verified" and retook the check blind. */}
            {!prev?.verified && ['DISPUTED', 'INSUFFICIENT'].includes(prev?.last_attempt?.state) && (
              <div style={{ border: `1px solid ${GOLD}`, background: '#FBF3E2', padding: '12px 14px', margin: '10px 0' }}>
                <p style={{ fontSize: 12, fontWeight: 600, letterSpacing: 1, textTransform: 'uppercase', color: GOLD_TEXT, margin: '0 0 4px' }}>
                  Last attempt couldn&rsquo;t be verified
                </p>
                <p style={{ fontSize: 13, color: '#555', lineHeight: 1.5, margin: 0 }}>
                  {prev.last_attempt.reason || 'The video didn’t match the submitted attempt.'}{' '}
                  Retake with good lighting and your ID and face clearly in frame.
                </p>
              </div>
            )}
            {/* Consent — a clear, bordered card so both required checkboxes (incl. 18+) read
                as distinct actions, not body text. The detail lives in the linked notices. */}
            <div style={consentCard}>
              <div style={consentHeader}>{t.consent_required || 'Before you start — both required'}</div>
              <label style={consentRow}>
                <input type="checkbox" checked={agreedBio} onChange={e => setAgreedBio(e.target.checked)} style={cbox} />
                <span style={{ ...consentTextStrong, borderLeft: `3px solid ${GOLD}`, paddingLeft: 10 }}>
                  {t.consent_bio}{' '}
                  <button type="button" onClick={() => setInfoModal('biometric')} style={linkBtn}>{t.consent_bio_link}</button>
                </span>
              </label>
              <label style={{ ...consentRow, marginTop: 12 }}>
                <input type="checkbox" checked={agreed18} onChange={e => setAgreed18(e.target.checked)} style={cbox} />
                <span style={{ ...consentTextStrong, borderLeft: `3px solid ${GOLD}`, paddingLeft: 10 }}>{t.consent_age}</span>
              </label>
            </div>
            <motion.button onClick={startId} disabled={!(agreedBio && agreed18)}
              whileHover={agreedBio && agreed18 ? { scale: 1.02 } : {}} whileTap={agreedBio && agreed18 ? { scale: 0.97 } : {}}
              style={{ ...btn, marginTop: 12, opacity: agreedBio && agreed18 ? 1 : 0.45,
                cursor: agreedBio && agreed18 ? 'pointer' : 'not-allowed' }}>
              START VERIFICATION
            </motion.button>
            <p style={fineprint}>
              {t.consent_fineprint_pre}{' '}
              <button type="button" onClick={() => setInfoModal('terms')} style={linkBtn}>{t.consent_terms_link}</button> {t.consent_and}{' '}
              <button type="button" onClick={() => setInfoModal('privacy')} style={linkBtn}>{t.consent_privacy_link}</button>.
            </p>
            {applying && (
              <button onClick={() => navigate('/profile')}
                style={{ ...btn, background: '#fff', color: '#777', border: '1px solid #e5e5e5', marginTop: 10 }}>
                Cancel
              </button>
            )}
          </motion.div>
        )}

        {(phase === 'capturing' || phase === 'submitting') && (
          <motion.div key="capture" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, transition: { duration: 0.18 } }} transition={{ duration: 0.25, ease: EASE }}>

            {captureStep === 'id' && !idPhoto && (
              <>
                <div style={{ position: 'relative', width: '100%', background: '#000', overflow: 'hidden', border: '1px solid #e5e5e5' }}>
                  <video ref={videoRef} autoPlay playsInline muted style={{ width: '100%', display: 'block' }} />
                  <div style={idGuideBox} />
                  <div style={idGuideLabel}>Center your ID in the frame</div>
                </div>
                <div style={{ display: 'flex', justifyContent: 'center', marginTop: 14 }}>
                  <motion.button onClick={captureIdPhoto} whileHover={{ scale: 1.02 }} whileTap={tapScale} style={{ ...btn, width: 'auto', padding: '14px 28px' }}>
                    <Camera size={14} strokeWidth={2} style={{ verticalAlign: '-2px', marginRight: 6 }} />CAPTURE ID PHOTO
                  </motion.button>
                </div>
              </>
            )}

            {captureStep === 'id' && idPhoto && (
              <>
                <div style={{ position: 'relative', width: '100%', background: '#000', overflow: 'hidden', border: '1px solid #e5e5e5' }}>
                  <img src={idPhoto.dataUrl} alt="Captured ID" style={{ width: '100%', display: 'block' }} />
                </div>
                <p style={{ fontSize: 12, color: '#999', margin: '10px 0 0', textAlign: 'center' }}>
                  Readable, no glare, all four corners visible?
                </p>
                <div style={{ display: 'flex', gap: 10, marginTop: 10 }}>
                  <motion.button onClick={retakeId} whileTap={tapScale}
                    style={{ ...btn, background: '#fff', color: '#1a1a1a', border: '1px solid #1a1a1a' }}>
                    <RotateCcw size={13} strokeWidth={2} style={{ verticalAlign: '-2px', marginRight: 6 }} />RETAKE
                  </motion.button>
                  <motion.button onClick={startLiveness} whileHover={{ scale: 1.02 }} whileTap={tapScale} style={btn}>
                    CONTINUE TO FACE CHECK
                  </motion.button>
                </div>
              </>
            )}

            {captureStep === 'liveness' && (
              <>
                <div style={{ position: 'relative', width: '100%', background: '#000', overflow: 'hidden', border: '1px solid #e5e5e5' }}>
                  <video ref={videoRef} autoPlay playsInline muted style={{ width: '100%', display: 'block', transform: 'scaleX(-1)' }} />
                  <canvas ref={canvasRef} style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', transform: 'scaleX(-1)' }} />
                  {elapsed < COUNTDOWN && (
                    <div style={overlayCenter}>
                      <AnimatePresence mode="wait">
                        <motion.span key={count} aria-label={`Starting in ${count}`}
                          initial={{ opacity: 0, scale: 1.3 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.8 }}
                          transition={{ duration: 0.25, ease: EASE }}
                          style={{ fontFamily: SERIF, fontSize: 90, fontWeight: 600, color: '#fff' }}>{count}</motion.span>
                      </AnimatePresence>
                    </div>
                  )}
                  {phase === 'capturing' && elapsed >= COUNTDOWN && (
                    <div style={promptBadge}>
                      Turn your head left, then right — then blink twice
                    </div>
                  )}
                </div>
                <div aria-live="polite" aria-atomic="true"
                  style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 12 }}>
                  <span style={{ fontSize: 11, letterSpacing: 1, textTransform: 'uppercase', color: '#777' }}>
                    turn <b style={{ color: '#1a1a1a' }}>{S.current.turnedLeft && S.current.turnedRight ? '✓' : '…'}</b>
                    {' '}· blinks <b style={{ fontFamily: SERIF, fontSize: 18, fontWeight: 600, color: '#1a1a1a', letterSpacing: 0 }}>{blinkCount}</b>/2 · {elapsed.toFixed(0)}s
                  </span>
                  {phase === 'submitting'
                    ? <span style={{ fontSize: 11, letterSpacing: 1, textTransform: 'uppercase', color: '#777' }}>verifying…</span>
                    : <motion.button onClick={stop} disabled={elapsed < MIN_SEC}
                        whileHover={elapsed < MIN_SEC ? {} : { scale: 1.03 }} whileTap={elapsed < MIN_SEC ? {} : tapScale}
                        style={{ ...btn, width: 'auto', opacity: elapsed < MIN_SEC ? 0.4 : 1 }}>
                        {elapsed < MIN_SEC ? `keep going (${Math.ceil(MIN_SEC - elapsed)}s)` : 'STOP & FINISH'}
                      </motion.button>}
                </div>
              </>
            )}
          </motion.div>
        )}

        {phase === 'result' && result && (
          <motion.div key="result" variants={staggerContainer(0.07)} initial="hidden" animate="show"
            exit={{ opacity: 0, transition: { duration: 0.18 } }} style={{ textAlign: 'center', padding: '20px 0' }}>
            {idPhoto && (
              <motion.img variants={fadeUp} src={idPhoto.dataUrl} alt="Captured ID" style={{ width: 140, border: '1px solid #e5e5e5', margin: '0 auto 14px', display: 'block' }} />
            )}
            {result.ok ? (
              <>
                <motion.div variants={scaleIn} style={{ fontFamily: SERIF, fontSize: 64, fontWeight: 600, color: GREEN }}>
                  {Math.round((result.faceDetectedPct + (result.turned ? 100 : 0) + Math.min(100, Math.round(result.blinks / 2 * 100))) / 3)}
                  <span style={{ fontSize: 22, color: '#999' }}>/100</span>
                </motion.div>
                <motion.div variants={fadeUp} style={{ fontSize: 11, letterSpacing: 2, textTransform: 'uppercase', fontWeight: 600, marginTop: 6, color: '#777' }}>
                  provisional · not yet verified
                </motion.div>
                {/* Breakdown of what the on-device read is made of. */}
                <motion.div variants={staggerContainer(0.08, 0.1)} initial="hidden" animate="show"
                  style={{ maxWidth: 320, margin: '18px auto 0', textAlign: 'left' }}>
                  {[['Face detected', result.faceDetectedPct, 'frames with a clear face'],
                    ['Head turn', result.turned ? 100 : 0, 'turned left and right'],
                    ['Blinks', Math.min(100, Math.round(result.blinks / 2 * 100)), `${result.blinks} detected`]].map(([label, val, hint]) => (
                    val == null ? null : (
                      <motion.div key={label} variants={fadeUp} style={{ margin: '10px 0' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, color: '#1a1a1a' }}>
                          <span>{label}<span style={{ color: '#aaa', fontSize: 11 }}> · {hint}</span></span><b>{val}</b>
                        </div>
                        <div style={{ height: 6, background: '#eee', borderRadius: 999, marginTop: 4 }}>
                          <motion.div initial={{ width: 0 }} animate={{ width: `${val}%` }} transition={{ duration: 0.5, ease: EASE, delay: 0.15 }}
                            style={{ height: '100%', background: GREEN, borderRadius: 999 }} />
                        </div>
                      </motion.div>
                    )
                  ))}
                </motion.div>
              </>
            ) : (
              <motion.p variants={fadeUp} style={{ color: GOLD_TEXT }}>Couldn&rsquo;t confirm your face. Keep your face centered and well-lit, then retake.</motion.p>
            )}

            {(applied || committed) ? (
              <motion.div variants={fadeUp} style={{ marginTop: 22, border: '1px solid #1F6F5C', background: '#E8F1EC', padding: '18px 16px' }}>
                <div style={{ fontFamily: SERIF, fontSize: 20, color: '#1a1a1a', marginBottom: 6 }}>Submitted for review <Check size={18} strokeWidth={2} color="#1F6F5C" style={{ verticalAlign: '-3px' }} /></div>
                <p style={{ fontSize: 13, color: '#1F6F5C', lineHeight: 1.55, margin: '0 0 14px' }}>
                  We&rsquo;ll review your identity verification and email you. Once approved you&rsquo;ll be able to switch to helping.
                </p>
                {/* Two-phase verification: the provisional read is above; here the
                    authoritative VIDEO recompute resolves to VERIFIED | DISPUTED | INSUFFICIENT. */}
                <AnimatePresence mode="wait">
                  {verifying && (
                    <motion.div key="verifying" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
                      transition={{ duration: 0.25, ease: EASE }} style={vpanel}>
                      <div style={vlabel}>Verifying</div>
                      <div style={{ fontFamily: SERIF, fontSize: 18, color: '#1a1a1a' }}>Verifying your ID and video…</div>
                      <p style={{ fontSize: 13, color: '#777', lineHeight: 1.5, margin: '6px 0 0' }}>
                        We&rsquo;re confirming your identity securely (usually under a minute). You can leave this
                        page — your profile updates when it&rsquo;s done.
                      </p>
                    </motion.div>
                  )}
                  {!verifying && attempt?.verificationState === 'VERIFIED' && (
                    <motion.div key="verified" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
                      transition={{ duration: 0.3, ease: EASE }} style={{ ...vpanel, border: `1px solid ${GREEN}`, background: '#E8F1EC' }}>
                      <div style={vlabel}>Verified</div>
                      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                        <motion.div initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ duration: 0.35, ease: EASE, delay: 0.1 }}
                          style={{ fontFamily: SERIF, fontSize: 40, fontWeight: 600, color: GREEN }}>
                          {attempt.authoritativeScore}<span style={{ fontSize: 18, color: '#999' }}>/100</span>
                        </motion.div>
                      </div>
                      <div style={{ fontSize: 13, color: GREEN, marginTop: 2 }}>
                        <motion.span initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ duration: 0.25, ease: EASE, delay: 0.3 }}
                          style={{ display: 'inline-flex', verticalAlign: '-2px' }}>
                          <Check size={13} strokeWidth={2} />
                        </motion.span> Verified from your ID and liveness video{attempt.tier ? ` · ${attempt.tier}` : ''}.
                      </div>
                      {attempt.reconciliation?.summary && (
                        <div style={{ fontSize: 11, color: '#888', marginTop: 6 }}>{attempt.reconciliation.summary}</div>
                      )}
                    </motion.div>
                  )}
                  {!verifying && attempt?.verificationState === 'DISPUTED' && (
                    <motion.div key="disputed" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
                      transition={{ duration: 0.3, ease: EASE }} style={{ ...vpanel, border: `1px solid ${GOLD}` }}>
                      <div style={vlabel}>Couldn&rsquo;t verify</div>
                      <p style={{ fontSize: 13, color: GOLD_TEXT, lineHeight: 1.5, margin: '4px 0 0' }}>
                        {attempt.reconciliation?.reason || 'The video didn’t match the submitted attempt.'}
                      </p>
                      <p style={{ fontSize: 11, color: '#aaa', marginTop: 6 }}>No credential was issued — retake with better lighting and your ID and face clearly in frame.</p>
                    </motion.div>
                  )}
                  {!verifying && attempt?.verificationState === 'INSUFFICIENT' && (
                    <motion.div key="insufficient" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
                      transition={{ duration: 0.3, ease: EASE }} style={vpanel}>
                      <div style={vlabel}>Not verified</div>
                      <p style={{ fontSize: 13, color: '#777', lineHeight: 1.5, margin: '4px 0 0' }}>
                        {attempt.reconciliation?.reason || 'Couldn’t confirm the video — your provisional check stands, but it isn’t verified.'}
                      </p>
                    </motion.div>
                  )}
                </AnimatePresence>
                <div style={{ fontSize: 11, color: '#aaa', margin: '10px 0 0' }}>Identity check — required before you can be listed as a helper.</div>
                <motion.button onClick={() => navigate(location.state?.returnTo || '/profile')} {...buttonPress} style={{ ...btn, marginTop: 14 }}>
                  {location.state?.returnTo ? 'DONE' : 'GO TO PROFILE'}
                </motion.button>
              </motion.div>
            ) : (
              <motion.div variants={fadeUp}>
                {err && <p style={{ color: ERROR, fontSize: 13, marginTop: 12 }}>{err}</p>}
                {result.ok && (
                  <p style={{ fontSize: 12, color: '#999', marginTop: 14, lineHeight: 1.5 }}>
                    We&rsquo;re verifying this take automatically. Not happy with it? Retake — only your verified take is kept.
                  </p>
                )}
                <div style={{ display: 'flex', gap: 10, marginTop: 14 }}>
                  <motion.button onClick={() => { pendingRef.current = null; setErr(''); setCaptureStep('id'); setIdPhoto(null); setPhase('intro') }} whileTap={tapScale}
                    style={{ ...btn, background: '#fff', color: '#1a1a1a', border: '1px solid #1a1a1a' }}>RETAKE</motion.button>
                  {result.ok && (
                    <motion.button onClick={commitSubmission} disabled={committing}
                      whileHover={committing ? {} : { scale: 1.02 }} whileTap={committing ? {} : { scale: 0.97 }}
                      style={{ ...btn, opacity: committing ? 0.6 : 1 }}>
                      {committing ? 'SUBMITTING…' : (applying ? 'SUBMIT APPLICATION' : 'SUBMIT FOR REVIEW')}
                    </motion.button>
                  )}
                </div>
              </motion.div>
            )}
          </motion.div>
        )}

        {phase === 'error' && (
          <motion.div key="error" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }} transition={{ duration: 0.25, ease: EASE }} style={{ padding: '20px 0' }}>
            <p style={{ color: ERROR }}>{err}</p>
            <motion.button onClick={() => { setCaptureStep('id'); setIdPhoto(null); setPhase('intro') }} whileTap={tapScale} style={{ ...btn, marginTop: 12 }}>BACK</motion.button>
          </motion.div>
        )}
      </AnimatePresence>
      </div>

      <InfoModal open={!!infoModal} onClose={() => setInfoModal(null)}
        title={{ terms: t.terms, privacy: t.privacy, biometric: t.biometric }[infoModal]}>
        {infoModal === 'terms' && <TermsContent />}
        {infoModal === 'privacy' && <PrivacyContent />}
        {infoModal === 'biometric' && <BiometricContent />}
      </InfoModal>
    </Shell>
  )
}

// Terminal verification states (recompute finished). Mirrors the backend state machine.
const TERMINAL_STATES = ['VERIFIED', 'DISPUTED', 'INSUFFICIENT']

// Client idempotency key for an attempt (one per capture). crypto.randomUUID needs a
// secure context (https/localhost — always true here); fall back just in case.
function _uuid() {
  try { return crypto.randomUUID() }
  catch {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
      const r = (Math.random() * 16) | 0
      return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16)
    })
  }
}

const vpanel = { background: '#fff', border: '1px solid #ddd', borderRadius: 4, padding: '14px 16px', margin: '18px 0 0', textAlign: 'left' }
const vlabel = { fontSize: 10, letterSpacing: 1.5, textTransform: 'uppercase', color: '#999', marginBottom: 4 }

const btn = {
  width: '100%', padding: '14px', borderRadius: 0, border: 'none', cursor: 'pointer',
  background: '#1F6F5C', color: '#fff', fontSize: 13, fontWeight: 600, letterSpacing: 1, textTransform: 'uppercase',
}
// Compact, Google-style consent styling — the heavy detail lives in the linked notices.
const consentRow = { display: 'flex', gap: 10, alignItems: 'flex-start' }
const cbox = { marginTop: 1, flexShrink: 0, width: 20, height: 20, accentColor: GREEN }
// Bordered card so the two REQUIRED consents (incl. 18+) read as distinct actions.
const consentCard = { margin: '18px 0 4px', border: '1px solid #d8d8d8', borderRadius: 6, padding: '14px 16px', background: '#fafafa' }
const consentHeader = { fontSize: 10, letterSpacing: 1.5, textTransform: 'uppercase', color: '#999', marginBottom: 12, fontWeight: 600 }
const consentTextStrong = { fontSize: 13, lineHeight: 1.5, color: '#1a1a1a' }
const linkBtn = {
  background: 'none', border: 'none', padding: 0, font: 'inherit',
  color: GREEN, textDecoration: 'underline', cursor: 'pointer',
}
const fineprint = { fontSize: 11, lineHeight: 1.5, color: '#999', textAlign: 'center', margin: '10px auto 0', maxWidth: 320 }
const overlayCenter = {
  position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center',
  background: 'rgba(0,0,0,0.45)',
}
// The ID-capture framing guide: a simple rounded rectangle so the applicant centers the
// card in frame, plus a caption underneath it.
const idGuideBox = {
  position: 'absolute', inset: '14% 8%', border: '2px dashed rgba(255,255,255,0.85)', borderRadius: 10,
  pointerEvents: 'none',
}
const idGuideLabel = {
  position: 'absolute', bottom: 10, left: 0, right: 0, textAlign: 'center',
  fontSize: 12, fontWeight: 600, letterSpacing: 0.5, color: '#fff', textShadow: '0 1px 3px rgba(0,0,0,0.6)',
}
// Small instruction banner over the liveness capture, top-center — tells the applicant
// what to do without covering their face.
const promptBadge = {
  position: 'absolute', top: 10, left: '50%', transform: 'translateX(-50%)',
  padding: '6px 14px', borderRadius: 999,
  background: 'rgba(0,0,0,0.55)', color: '#fff',
  fontSize: 11, fontWeight: 600, letterSpacing: 0.3, textAlign: 'center', whiteSpace: 'nowrap',
}
