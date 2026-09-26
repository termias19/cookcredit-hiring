import usePlaybackView from '../hooks/usePlaybackView'
import './CandidateVideoPlayer.css'

export default function PlaybackViewControl() {
  const [landmarks, setLandmarks] = usePlaybackView()
  return <div className="cc-playback-view" role="group" aria-label="Recording viewing preference">
    <button type="button" aria-pressed={!landmarks} onClick={() => setLandmarks(false)}>Video only</button>
    <button type="button" aria-pressed={landmarks} onClick={() => setLandmarks(true)}>Landmarks</button>
  </div>
}
