import test from 'node:test'
import assert from 'node:assert/strict'
import { loadAccountProfile } from '../src/utils/loadAccountProfile.js'
const account = { uid: 'new', email: 'new@example.test', getIdToken: async () => 'test-token' }
test('Google employer creation survives unavailable storage without granting a seat', async () => {
  const calls = []
  const values = { name: 'Chef', roles: ['eater'], activeRole: 'business', createOnly: true }
  const result = await loadAccountProfile(account, {
    suppliedProfile: values, readDraft() { throw Error('denied') }, clearDraft() { throw Error('denied') },
    request: async (path, token, options) => { calls.push([path, token, options]); return { id: 'new' } },
  })
  assert.equal(result.id, 'new')
  assert.deepEqual(JSON.parse(calls[0][2].body), values)
  assert.equal(calls[1][0], '/api/auth/me')
})
test('another account recovery draft is never replayed', async () => {
  const calls = []
  await loadAccountProfile(account, { readDraft: () => ({ uid: 'other', profile: { name: 'Other' } }),
    clearDraft: () => assert.fail(), request: async path => { calls.push(path); return { id: 'new' } } })
  assert.deepEqual(calls, ['/api/auth/me'])
})
test('transient and forbidden failures do not trigger account recreation', async () => {
  for (const status of [403, 503]) {
    let calls = 0
    await assert.rejects(loadAccountProfile(account, { readDraft: () => null,
      request: async () => { calls++; throw Object.assign(Error('failed'), { status }) } }))
    assert.equal(calls, 1)
  }
})
test('failed sync retains its recovery draft; only missing profiles self-heal', async () => {
  let cleared = false
  await assert.rejects(loadAccountProfile(account, { suppliedProfile: { createOnly: true },
    clearDraft: () => { cleared = true }, request: async () => { throw Error('offline') } }))
  assert.equal(cleared, false)
  const calls = []
  await loadAccountProfile(account, { readDraft: () => null, request: async (path, token, options) => {
    calls.push([path, options]); if (calls.length === 1) throw Object.assign(Error('missing'), { status: 404 })
    return { id: 'new' }
  } })
  assert.deepEqual(calls.map(c => c[0]), ['/api/auth/me', '/api/auth/sync', '/api/auth/me'])
  assert.equal(JSON.parse(calls[1][1].body).createOnly, true)
})
