/**
 * Shared HTTP client.
 *
 * Centralizes what every API helper was re-implementing inline: the base URL,
 * the `Authorization: Bearer <firebase id token>` header, JSON vs FormData
 * bodies, response parsing, request timeouts, and a one-shot 401
 * refresh-and-retry (when a firebase `auth` object is available to mint a
 * fresh token).
 *
 * Behavior contract (matches the pre-refactor helpers):
 *   - default: returns the parsed JSON body whether or not res.ok, so callers
 *     that inspect `{ error }` keep working (auth/stripe helpers rely on this).
 *   - { throwOnError: true }: throws on a non-2xx with a normalized message
 *     (the skill-test helpers want this).
 *   - FormData bodies: passed through untouched; Content-Type is left unset so
 *     the browser adds the multipart boundary.
 *   - Timeouts always throw (there is no body to return): 20s for JSON,
 *     120s for FormData (video/photo uploads on slow connections), override
 *     with { timeoutMs }.
 */

import { errorReference } from './errorReference.js'
import { PREVIEW } from '../config'
import { previewBusinessRequest } from '../data/previewBusinessApi'

const BASE = import.meta.env.VITE_API_URL || 'http://localhost:5000'

const JSON_TIMEOUT_MS = 20_000
const UPLOAD_TIMEOUT_MS = 120_000

/** Resolve a bearer token from either an explicit token or a firebase auth obj. */
async function resolveToken({ token, auth, forceRefresh = false }) {
  if (token) return token
  if (auth?.currentUser) return auth.currentUser.getIdToken(forceRefresh)
  return null
}

export async function http(path, opts = {}) {
  if (PREVIEW) {
    const preview = await previewBusinessRequest(path, opts)
    if (preview.handled) return preview.data
  }
  const {
    method = 'GET',
    body,
    token,
    auth,
    formData,
    throwOnError = false,
    headers: extraHeaders,
    timeoutMs,
  } = opts

  let fetchBody
  const baseHeaders = { ...(extraHeaders || {}) }
  if (formData) {
    fetchBody = formData                 // browser sets multipart Content-Type
  } else if (body !== undefined) {
    baseHeaders['Content-Type'] = 'application/json'
    fetchBody = JSON.stringify(body)
  }

  const limit = timeoutMs ?? (formData ? UPLOAD_TIMEOUT_MS : JSON_TIMEOUT_MS)

  const doFetch = async (bearer) => {
    const headers = { ...baseHeaders }
    if (bearer) headers['Authorization'] = `Bearer ${bearer}`
    const ctl = new AbortController()
    const timer = setTimeout(() => ctl.abort(), limit)
    try {
      return await fetch(`${BASE}${path}`, {
        method: fetchBody && method === 'GET' ? 'POST' : method,
        headers,
        body: fetchBody,
        signal: ctl.signal,
      })
    } finally {
      clearTimeout(timer)
    }
  }

  let res
  try {
    res = await doFetch(await resolveToken({ token, auth }))
    // A 401 with a live firebase session usually means a stale/revoked ID token:
    // force-refresh once and retry. Only possible when `auth` was passed (an
    // explicit `token` can't be refreshed here).
    if (res.status === 401 && auth?.currentUser && !token) {
      const fresh = await resolveToken({ auth, forceRefresh: true }).catch(() => null)
      if (fresh) res = await doFetch(fresh)
    }
  } catch (e) {
    if (e?.name === 'AbortError') {
      throw new Error('Request timed out — check your connection and try again.')
    }
    throw e
  }

  if (res.ok && opts.responseType === 'blob') return res.blob()
  const data = await res.json().catch(() => ({}))
  const reference = errorReference(data, res)
  if (reference && data && typeof data === 'object') {
    data.requestId = reference
    data.error = `${data.error || 'Request failed'}. Reference: ${reference}`
  }
  if (throwOnError && !res.ok) {
    const error = new Error(data?.error || `${path} failed (${res.status})`)
    error.status = res.status
    error.code = data?.code
    error.requestId = reference
    throw error
  }
  return data
}

export { BASE }
export default http
