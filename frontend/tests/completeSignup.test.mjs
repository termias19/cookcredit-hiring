import test from 'node:test'
import assert from 'node:assert/strict'
import { completeSignup } from '../src/utils/completeSignup.js'

function setup(overrides = {}) {
  const calls = []
  return { calls, options: { user: { uid: 'owner' }, profile: { name: ' Cook ', activeRole: 'business' },
    updateName: async (_, name) => calls.push(['name', name]),
    remember: (uid, profile) => calls.push(['remember', uid, profile.activeRole]),
    clear: () => calls.push('clear'), sync: async () => calls.push('sync'),
    verify: async () => calls.push('verify'), ...overrides } }
}

test('profile outage still sends verification and retains recoverable employer intent', async () => {
  const { options, calls } = setup({ sync: async () => { throw new Error('503') } })
  assert.deepEqual(await completeSignup(options), { profileSynced: false, verificationSent: true })
  assert.deepEqual(calls, [['name', 'Cook'], ['remember', 'owner', 'business'], 'verify'])
})
test('email outage does not turn a created account into a failed signup', async () => {
  const { options, calls } = setup({ verify: async () => { throw new Error('quota') } })
  assert.deepEqual(await completeSignup(options), { profileSynced: true, verificationSent: false })
  assert.ok(calls.includes('clear'))
})
test('name update and both provider failures remain recoverable', async () => {
  const fail = async () => { throw new Error('offline') }
  const { options, calls } = setup({ updateName: fail, sync: fail, verify: fail })
  assert.deepEqual(await completeSignup(options), { profileSynced: false, verificationSent: false })
  assert.deepEqual(calls, [['remember', 'owner', 'business']])
})
test('successful signup clears the recovery draft after profile creation', async () => {
  const { options, calls } = setup()
  assert.deepEqual(await completeSignup(options), { profileSynced: true, verificationSent: true })
  assert.deepEqual(calls.slice(-3), ['sync', 'clear', 'verify'])
})
