// Send bounded error categories through the existing API. Never send Error
// objects, messages, stacks, URLs, query strings, tokens or account identifiers.
let settings
let stop
const sent = new Map()

export function screenCategory(path = '') {
  if (path === '/') return 'landing'
  if (/^\/(login|signup|forgot|account|request-access)(\/|$)/.test(path)) return 'auth'
  if (/^\/(business|owner)(\/|$)/.test(path)) return 'manager'
  if (/^\/(apply|invite|applicant)(\/|$)/.test(path)) return 'applicant'
  if (/^\/landing\/assessment(\/|$)/.test(path)) return 'assessment'
  return 'other'
}

export function homeScreenCategory(hash = '') {
  if (/^#(sign-in|account\/)/.test(hash)) return 'auth'
  if (/^#team(?:$|\?)/.test(hash)) return 'home_operator'
  if (/^#(payout|helping)(?:$|\?)/.test(hash)) return 'home_helper'
  if (/^#(visit\/|visits$|request$)/.test(hash)) return 'home_customer'
  return 'landing'
}

export function reportClientError(code) {
  if (!settings?.enabled || globalThis.navigator?.onLine === false) return ''
  const allowed = ['render_error', 'unhandled_error', 'unhandled_rejection',
    'api_network_error', 'api_timeout', 'api_response_invalid', 'google_signin_error']
  if (!allowed.includes(code)) return ''
  try {
    const screen = settings.product === 'home' ? homeScreenCategory(globalThis.location?.hash) : screenCategory(globalThis.location?.pathname)
    const key = `${code}:${screen}`
    if (sent.has(key)) return sent.get(key)
    if (sent.size >= 5) return ''
    const reference = globalThis.crypto.randomUUID().replaceAll('-', '')
    sent.set(key, reference)
    const release = /^[a-f0-9]{40}$/.test(settings.release || '') ? settings.release : 'unrecorded'
    // Failure reporting must never delay or retry a customer's action.
    const path = settings.product === 'home' ? '/api/home/observability/client-error' : '/api/observability/client-error'
    Promise.resolve(globalThis.fetch(`${settings.apiOrigin}${path}`, {
      method: 'POST', credentials: 'omit', referrerPolicy: 'no-referrer', keepalive: true,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code, screen, release, reference }),
    })).catch(() => {})
    return reference
  } catch { return '' }
}

export function startErrorReporting(options) {
  if (stop) return stop
  settings = { ...options }
  if (!options.enabled || !/^https:\/\/[^/]+$/.test(options.apiOrigin || '')) {
    settings.enabled = false
    return () => {}
  }
  const onError = () => reportClientError('unhandled_error')
  const onRejection = () => reportClientError('unhandled_rejection')
  globalThis.addEventListener('error', onError)
  globalThis.addEventListener('unhandledrejection', onRejection)
  stop = () => {
    globalThis.removeEventListener('error', onError)
    globalThis.removeEventListener('unhandledrejection', onRejection)
    stop = undefined
    settings = undefined
    sent.clear()
  }
  return stop
}
