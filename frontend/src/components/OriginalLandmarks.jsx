import { useEffect, useRef, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { getCandidateVideo } from '../utils/Api'
import { containedFrame, HAND_EDGES } from '../utils/landmarkGeometry'
import { validateOriginalLandmarks, landmarkFrameAt } from '../utils/originalLandmarks'

export default function OriginalLandmarks({ videoRef, cookId, roleId, attemptId }) {
  const { user } = useAuth(), canvasRef = useRef(null)
  const [status, setStatus] = useState('Loading original landmarks…')
  useEffect(() => {
    const controller = new AbortController()
    let frames, engineRenderer, animation, videoCallback, disposed = false
    const video = videoRef.current, canvas = canvasRef.current, ctx = canvas.getContext('2d')
    const timer = setTimeout(() => controller.abort(), 15000)
    function draw() {
      if (disposed) return
      const rect = canvas.getBoundingClientRect()
      canvas.width = Math.round(rect.width); canvas.height = Math.round(rect.height)
      ctx.clearRect(0, 0, canvas.width, canvas.height)
      const frame = containedFrame(canvas.width, canvas.height, video.videoWidth, video.videoHeight)
      const row = frames && landmarkFrameAt(frames, video.currentTime)
      if (row && frame && row[3] && engineRenderer) {
        ctx.save(); ctx.translate(frame.x,frame.y); ctx.scale(frame.width/row[3].width,frame.height/row[3].height)
        ctx.beginPath(); ctx.rect(0,0,row[3].width,row[3].height); ctx.clip()
        engineRenderer(ctx,row); ctx.restore()
      } else if (row && frame && !row[3]) {
        row.slice(1,3).forEach((hand, index) => {
          if (!hand) return
          ctx.strokeStyle = index === 0 ? '#00dc00' : '#b400b4'
          ctx.fillStyle = ctx.strokeStyle; ctx.lineWidth = index === 0 ? 3 : 2
          const point = p => [frame.x + p[0] * frame.width, frame.y + p[1] * frame.height]
          for (const [a,b] of HAND_EDGES) { ctx.beginPath(); ctx.moveTo(...point(hand[a])); ctx.lineTo(...point(hand[b])); ctx.stroke() }
          for (const p of hand) { ctx.beginPath(); ctx.arc(...point(p), 2, 0, Math.PI * 2); ctx.fill() }
        })
      }
    }
    function tick() {
      draw()
      if (disposed) return
      if (video.requestVideoFrameCallback) videoCallback = video.requestVideoFrameCallback(tick)
      else animation = requestAnimationFrame(tick)
    }
    const resize = new ResizeObserver(draw); resize.observe(canvas)
    video.addEventListener('seeked', draw); video.addEventListener('loadedmetadata', draw)
    async function load() {
      try {
        if (!user || !cookId || !attemptId) { setStatus('Original landmarks are unavailable for this recording.'); return }
        const token = await user.getIdToken()
        const result = await getCandidateVideo({token, cookId, roleId, attemptId, landmarks:true})
        if (disposed) return
        if (result?.attemptId !== attemptId) throw new Error('Attempt mismatch')
        if (!result.landmarksUrl) { setStatus('Original landmarks were not saved with this recording.'); return }
        const response = await fetch(result.landmarksUrl, {signal:controller.signal, credentials:'omit', cache:'no-store'})
        if (!response.ok) throw new Error('Unavailable')
        const reader = response.body.getReader(), chunks = []
        let size = 0
        while (true) {
          const {done,value} = await reader.read(); if (done) break
          size += value.length
          if (size > 4 * 1024 * 1024) { await reader.cancel(); throw new Error('Too large') }
          chunks.push(value)
        }
        const bytes = new Uint8Array(size); let offset = 0
        for (const part of chunks) { bytes.set(part,offset); offset += part.length }
        const capture = JSON.parse(new TextDecoder().decode(bytes))
        frames = validateOriginalLandmarks(capture)
        if (disposed) return
        if (frames[0].length === 4) {
          const module = await import(/* @vite-ignore */ `/assessment-overlays/${capture.renderer}.mjs`)
          if (disposed) return
          engineRenderer = module.drawOriginalEngineOverlay
        }
        setStatus(engineRenderer ? 'Original engine hand and knife overlay' : 'Original hand landmarks  -  knife overlay was not saved'); tick()
      } catch { if (!disposed) setStatus('Original landmarks could not load. Video remains available.') }
      finally { clearTimeout(timer) }
    }
    void load()
    return () => {
      disposed = true; clearTimeout(timer); controller.abort(); resize.disconnect()
      video.removeEventListener('seeked',draw); video.removeEventListener('loadedmetadata',draw)
      cancelAnimationFrame(animation)
      if (videoCallback !== undefined) video.cancelVideoFrameCallback(videoCallback)
      ctx.clearRect(0,0,canvas.width,canvas.height)
    }
  }, [user, cookId, roleId, attemptId, videoRef])
  return <><canvas ref={canvasRef} className="cc-playback-landmarks" aria-hidden="true"/><span className="cc-landmark-status" role="status">{status}</span></>
}

