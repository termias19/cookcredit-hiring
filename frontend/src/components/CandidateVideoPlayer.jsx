import { useEffect, useRef, useState } from 'react'
import { Play, Pause, Volume2, VolumeX } from 'lucide-react'
import usePlaybackView from '../hooks/usePlaybackView'
import PlaybackViewControl from './PlaybackViewControl'
import OriginalLandmarks from './OriginalLandmarks'
import './CandidateVideoPlayer.css'

export default function CandidateVideoPlayer({ url, active = true, reel = false, onRetry, cookId, roleId, attemptId, label = 'Candidate assessment recording' }) {
  const video = useRef(null)
  const [landmarks] = usePlaybackView()
  const [status, setStatus] = useState('loading')
  const [playing, setPlaying] = useState(false), [muted, setMuted] = useState(true)
  const [position, setPosition] = useState(0), [duration, setDuration] = useState(0)
  useEffect(() => {
    if (!url || !active) return undefined
    const timer = window.setTimeout(() => setStatus(current => current === 'ready' ? current : 'stalled'), 15000)
    return () => window.clearTimeout(timer)
  }, [url, active])
  useEffect(() => {
    const element = video.current
    const update = () => {
      if (!active || document.hidden) element?.pause()
      else if (reel && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) element?.play().catch(() => {})
    }
    update()
    document.addEventListener('visibilitychange', update)
    return () => { document.removeEventListener('visibilitychange', update); element?.pause() }
  }, [active, reel, url])
  const toggle = () => { if (video.current?.paused) video.current.play().catch(() => setStatus('error')); else video.current?.pause() }
  return <div className={`cc-candidate-player${reel ? ' cc-player-reel' : ''}`}>
    {!reel && <div className="cc-report-view"><PlaybackViewControl /></div>}
    <video ref={video} src={url} crossOrigin="anonymous" controls={!reel} playsInline muted={muted} loop={reel} preload={active ? 'metadata' : 'none'}
      aria-label={label} onLoadedMetadata={event => { setStatus('ready'); setDuration(event.currentTarget.duration) }} onCanPlay={() => setStatus('ready')}
      onError={() => setStatus('error')} onPlaying={() => { setStatus('ready'); setPlaying(true) }} onPause={() => setPlaying(false)}
      onTimeUpdate={event => setPosition(event.currentTarget.currentTime)} />
    {landmarks && active && <OriginalLandmarks videoRef={video} cookId={cookId} roleId={roleId} attemptId={attemptId} />}
    {reel && <>
      <button className="cc-video-tap" onClick={toggle} aria-label={playing ? 'Pause recording' : 'Play recording'}>{!playing && <Play size={36}/>}</button>
      <div className="cc-reel-transport">
        <button onClick={toggle} aria-label={playing ? 'Pause recording' : 'Play recording'}>{playing ? <Pause/> : <Play/>}</button>
        <button onClick={() => setMuted(value => !value)} aria-label={muted ? 'Unmute recording' : 'Mute recording'}>{muted ? <VolumeX/> : <Volume2/>}</button>
        <input type="range" aria-label="Recording position" min="0" max={Number.isFinite(duration) && duration > 0 ? duration : 1} step="0.1" value={position}
          onChange={event => { if (video.current) video.current.currentTime = Number(event.target.value) }} />
      </div>
    </>}
    {(status === 'error' || status === 'stalled') && <div className="cc-video-recovery" role="status">
      <p>This player could not open the recording. Retry or open it in your browser.</p>
      <button type="button" onClick={onRetry}>Retry video</button>
      <a href={url} target="_blank" rel="noopener noreferrer">Open recording</a>
    </div>}
  </div>
}
