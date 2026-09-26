import { useEffect, useRef } from 'react'
export default function SplashScreen({ onFinished }) {
  const finish = useRef(onFinished)
  useEffect(() => { finish.current = onFinished })
  useEffect(() => { finish.current() }, [])
  return <div role="status" aria-label="Loading CookCredit" style={{ position: 'fixed', inset: 0, background: '#FEFDFB', display: 'grid', placeContent: 'center', justifyItems: 'center', gap: 14 }}>
    <img src="/cookcredit-mark-orange.svg" alt="" width="56" height="44" />
    <span style={{ fontFamily: 'var(--cc-display)', fontSize: 30 }}>CookCredit</span>
  </div>
}
