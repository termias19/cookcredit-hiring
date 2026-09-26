import { useSyncExternalStore } from 'react'

const KEY = 'cookcredit.playback.landmarks'
const EVENT = 'cookcredit-playback-view'
let memory = false
const read = () => { try { memory = localStorage.getItem(KEY) === 'on' } catch { /* Private browsing may deny storage. */ } return memory }
const subscribe = callback => {
  window.addEventListener(EVENT, callback)
  window.addEventListener('storage', callback)
  return () => { window.removeEventListener(EVENT, callback); window.removeEventListener('storage', callback) }
}
export default function usePlaybackView() {
  const enabled = useSyncExternalStore(subscribe, read, () => false)
  const setEnabled = value => {
    memory = Boolean(value)
    try { localStorage.setItem(KEY, value ? 'on' : 'off') } catch { /* Keep the in-memory preference. */ }
    window.dispatchEvent(new Event(EVENT))
  }
  return [enabled, setEnabled]
}
