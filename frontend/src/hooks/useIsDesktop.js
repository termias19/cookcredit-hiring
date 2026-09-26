import { useState, useEffect } from 'react'

/**
 * True when the viewport is desktop-width. Drives the responsive Shell:
 * mobile -> phone-frame app layout; desktop -> top-nav website layout.
 */
export default function useIsDesktop(query = '(min-width: 900px)') {
  const get = () => typeof window !== 'undefined' && window.matchMedia(query).matches
  const [isDesktop, setIsDesktop] = useState(get)

  // If the query prop ever changes, re-derive during render (React's sanctioned
  // "adjust state on prop change" pattern) instead of a sync set inside the effect.
  const [prevQuery, setPrevQuery] = useState(query)
  if (prevQuery !== query) {
    setPrevQuery(query)
    setIsDesktop(get())
  }

  useEffect(() => {
    const mq = window.matchMedia(query)
    const onChange = (e) => setIsDesktop(e.matches)
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [query])

  return isDesktop
}
