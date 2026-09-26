import test from 'node:test'
import assert from 'node:assert/strict'
import { verifyAccountLink } from '../src/utils/verifyAccountLink.js'

function setup(user = { uid: 'candidate', email: 'candidate@example.test' }) {
  const calls = []
  const options = { auth: { currentUser: user }, code: 'test-code',
    checkCode: async () => ({ operation: 'VERIFY_EMAIL', data: { email: 'candidate@example.test' } }),
    applyCode: async () => calls.push('apply'),
    complete: async () => { calls.push('complete'); return { id: 'candidate', roles: ['eater'] } } }
  return { options, calls }
}
test('verification returns only the matching candidate profile', async () => {
  const { options, calls } = setup()
  assert.equal((await verifyAccountLink(options)).profile.id, 'candidate')
  assert.deepEqual(calls, ['apply', 'complete'])
})
test('an existing employer session is never refreshed or used by a candidate link', async () => {
  const { options, calls } = setup({ uid: 'employer', email: 'owner@example.test' })
  assert.equal((await verifyAccountLink(options)).profile, null)
  assert.deepEqual(calls, ['apply'])
})
test('a link in a signed-out browser verifies without inventing a login session', async () => {
  const { options, calls } = setup(null)
  assert.equal((await verifyAccountLink(options)).profile, null)
  assert.deepEqual(calls, ['apply'])
})
test('account changes during profile load cannot route into the new session', async () => {
  const { options } = setup()
  options.complete = async () => { options.auth.currentUser = { uid: 'employer', email: 'owner@example.test' }; return { id: 'employer' } }
  assert.equal((await verifyAccountLink(options)).profile, null)
})
test('a profile outage after code consumption preserves successful verification', async () => {
  const { options, calls } = setup()
  options.complete = async () => { throw new Error('offline') }
  assert.deepEqual(await verifyAccountLink(options), { email: 'candidate@example.test', profile: null })
  assert.deepEqual(calls, ['apply'])
})
test('invalid and wrong-purpose links cannot consume a verification action', async () => {
  const { options, calls } = setup()
  options.checkCode = async () => ({ operation: 'PASSWORD_RESET', data: { email: 'candidate@example.test' } })
  await assert.rejects(verifyAccountLink(options))
  assert.deepEqual(calls, [])
})
