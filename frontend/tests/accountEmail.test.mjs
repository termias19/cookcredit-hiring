import test from 'node:test'
import assert from 'node:assert/strict'
import { createAccountEmail } from '../src/utils/accountEmail.js'

function setup(overrides = {}) {
  const user = { emailVerified: false }
  const auth = { currentUser: user }
  const calls = []
  const service = createAccountEmail({
    auth, ready: true, continueUrl: 'https://cookcredit.com',
    attest: async () => calls.push('attested'),
    sendVerification: async (...args) => calls.push(['verify', ...args]),
    sendReset: async (...args) => calls.push(['reset', ...args]), ...overrides,
  })
  return { user, auth, calls, service }
}

test('unverified branding prevents both kinds of email before any provider call', async () => {
  const { service, user, calls } = setup({ ready: false })
  await assert.rejects(service.verification(user, 'EN'), /temporarily unavailable/)
  await assert.rejects(service.reset('customer@example.test', 'EN'), /temporarily unavailable/)
  assert.deepEqual(calls, [])
})

test('verification only uses the signed-in account and preserves the chosen language', async () => {
  const { service, user, auth, calls } = setup()
  await assert.rejects(service.verification({ emailVerified: false }, 'EN'), /Sign in/)
  await service.verification(user, 'ES')
  assert.equal(auth.languageCode, 'es')
  assert.equal(calls[0], 'attested')
  assert.deepEqual(calls[1], ['verify', user, { url: 'https://cookcredit.com/', handleCodeInApp: false }])
  user.emailVerified = true
  await service.verification(user, 'EN')
  assert.equal(calls.length, 2)
})

test('reset hides account absence but reports delivery failure', async () => {
  const missing = setup({ sendReset: async () => { throw { code: 'auth/user-not-found' } } })
  await missing.service.reset('unknown@example.test', 'EN')
  for (const code of ['auth/network-request-failed', 'auth/too-many-requests', 'auth/invalid-email']) {
    const { service } = setup({ sendReset: async () => { throw { code } } })
    await assert.rejects(service.reset('customer@example.test', 'EN'), e => e.code === code)
  }
})

test('reset normalizes the address and never calls the application outbox', async () => {
  const { service, auth, calls } = setup()
  await service.reset(' customer@example.test ', 'EN')
  assert.equal(auth.languageCode, 'en')
  assert.equal(calls[1][2], 'customer@example.test')
})

test('reject project-id links, deceptive domains, insecure URLs and extra query data', async () => {
  for (const continueUrl of ['https://old-project.firebaseapp.com', 'https://cookcredit.com.evil.test',
    'http://cookcredit.com', 'https://user@cookcredit.com', 'https://cookcredit.com/?next=bad']) {
    const { service, calls } = setup({ continueUrl })
    await assert.rejects(service.reset('customer@example.test', 'EN'), /destination/)
    assert.deepEqual(calls, [])
  }
})

test('an attestation failure never sends email', async () => {
  const { service, user, calls } = setup({ attest: async () => { throw new Error('attestation unavailable') } })
  await assert.rejects(service.verification(user, 'EN'), /attestation/)
  await assert.rejects(service.reset('customer@example.test', 'EN'), /attestation/)
  assert.deepEqual(calls, [])
})

test('only the exact staging login may be used as a staging continuation', async () => {
  const continueUrl = 'https://cookcredit-hiring-staging.web.app/login'
  await setup({ continueUrl, environment: 'staging' }).service.reset('customer@example.test', 'EN')
  for (const options of [{ continueUrl }, { continueUrl: continueUrl+'?next=evil', environment: 'staging' },
    { continueUrl: 'https://other-staging.web.app/login', environment: 'staging' },
    { continueUrl: 'https://cookcredit-hiring-staging.web.app/redirect', environment: 'staging' }]) {
    await assert.rejects(setup(options).service.reset('customer@example.test', 'EN'), /destination/)
  }
})

test('Google branded mail uses the attested outbox, with the signed-in identity for verification', async () => {
  const requests = []
  const { service, user, calls } = setup({ provider: 'google_smtp', request: async (...args) => requests.push(args) })
  await service.verification(user, 'EN')
  await service.reset(' customer@example.test ', 'EN')
  assert.deepEqual(calls, ['attested', 'attested'])
  assert.deepEqual(requests, [['verification', user, {}], ['password-reset', null, { email: 'customer@example.test' }]])
})

test('a branded-delivery failure never falls back to a duplicate native email', async () => {
  const { service, user, calls } = setup({ provider: 'google_smtp', request: async () => { throw new Error('outbox unavailable') } })
  await assert.rejects(service.verification(user, 'EN'), /outbox unavailable/)
  await assert.rejects(service.reset('customer@example.test', 'EN'), /outbox unavailable/)
  assert.deepEqual(calls, ['attested', 'attested'])
})
