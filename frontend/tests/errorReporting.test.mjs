import test from 'node:test'
import assert from 'node:assert/strict'
import { reportClientError, screenCategory, startErrorReporting } from '../src/utils/errorReporting.js'

test('route categories never contain applicant or invitation identifiers', () => {
  assert.equal(screenCategory('/apply/private-token'), 'applicant')
  assert.equal(screenCategory('/business/candidates/private-person'), 'manager')
  assert.equal(screenCategory('/login?email=private@example.test'), 'other')
})

test('reports deduplicate, cap volume and transmit only allowlisted metadata', async () => {
  const saved = { fetch: globalThis.fetch, add: globalThis.addEventListener, remove: globalThis.removeEventListener }
  const calls = [];const listeners = new Map()
  globalThis.fetch = async (url, options) => { calls.push({ url, options }) }
  globalThis.addEventListener = (name, listener) => listeners.set(name, listener)
  globalThis.removeEventListener = name => listeners.delete(name)
  const stop = startErrorReporting({ enabled: true, apiOrigin: 'https://api.example.test', release: 'a'.repeat(40) })
  try {
    assert.equal(calls.length, 0) // No work on successful navigation.
    const ref = reportClientError('render_error')
    assert.match(ref, /^[a-f0-9]{32}$/)
    assert.equal(reportClientError('render_error'), ref)
    listeners.get('error')({ error: new Error('PRIVATE_TOKEN') })
    listeners.get('unhandledrejection')({ reason: 'private@example.test' })
    reportClientError('api_timeout');reportClientError('api_network_error')
    assert.equal(reportClientError('api_response_invalid'), '') // Five reports per page lifetime.
    assert.equal(calls.length, 5)
    for (const { url, options } of calls) {
      assert.equal(url, 'https://api.example.test/api/observability/client-error')
      assert.equal(options.credentials, 'omit')
      assert.equal(options.referrerPolicy, 'no-referrer')
      assert.deepEqual(Object.keys(JSON.parse(options.body)).sort(), ['code', 'reference', 'release', 'screen'])
      assert.ok(!JSON.stringify(options).includes('PRIVATE_TOKEN'))
      assert.ok(!JSON.stringify(options).includes('private@example.test'))
    }
  } finally {
    stop();globalThis.fetch = saved.fetch;globalThis.addEventListener = saved.add;globalThis.removeEventListener = saved.remove
  }
})

test('preview and local development reporting stays disabled', () => {
  const stop = startErrorReporting({ enabled: false, apiOrigin: 'http://localhost:5000' })
  assert.equal(reportClientError('render_error'), '')
  stop()
})
