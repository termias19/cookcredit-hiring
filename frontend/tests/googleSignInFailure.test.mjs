import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { googleSignInFailure } from '../src/utils/googleSignInFailure.js'

test('Google errors retain safe references, distinguish API access, and do not expose provider data', () => {
  assert.equal(googleSignInFailure({ code: 'auth/popup-closed-by-user' }), '')
  assert.match(googleSignInFailure({ code: 'auth/internal-error', message: 'private-token' }), /Reference: auth\/internal-error/)
  assert.doesNotMatch(googleSignInFailure({ code: 'secret-value', message: 'private-token' }), /secret-value|private-token/)
  assert.match(googleSignInFailure({ status: 403, code: 'staging_access_denied' }), /testing access/)
  assert.match(googleSignInFailure({ code: 'auth/popup-blocked' }), /Allow the Google sign-in window/)
})

test('deployed app policy allows the Firebase Google popup loader without changing assessment policy', async () => {
  const config = JSON.parse(await readFile(new URL('../firebase.json', import.meta.url), 'utf8'))
  const policy = config.hosting.headers.filter(row => row.source === '**').flatMap(row => row.headers).find(row => row.key === 'Content-Security-Policy').value
  const scripts = policy.split(';').find(part => part.trim().startsWith('script-src ')).trim().split(/\s+/).slice(1)
  assert.ok(scripts.includes('https://apis.google.com'))
  assert.ok(!scripts.includes('*') && !scripts.includes('https:') && !scripts.includes("'unsafe-inline'"))
  const assessment = config.hosting.headers.find(row => row.source === '/landing/assessment/**').headers.find(row => row.key === 'Content-Security-Policy').value
  assert.ok(!assessment.includes('https://apis.google.com'))
})
