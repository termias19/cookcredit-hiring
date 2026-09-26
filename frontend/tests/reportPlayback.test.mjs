import test from 'node:test'
import assert from 'node:assert/strict'
import { reportPlayback } from '../src/utils/reportPlayback.js'

test('playback pins the displayed attempt even when a later attempt exists', async () => {
  const input = {token:'test', cookId:'candidate', roleId:'role', attemptId:'shown-attempt'}
  const url = await reportPlayback({...input, request: async args => {
    assert.deepEqual(args, input)
    return {attemptId:'shown-attempt', videoUrl:'https://example.test/recording'}
  }})
  assert.equal(url, 'https://example.test/recording')
})

test('missing report or authentication never requests an arbitrary latest video', async () => {
  for (const input of [{token:'test'}, {attemptId:'shown-attempt'}]) {
    await assert.rejects(reportPlayback({...input, request: () => assert.fail('must not request')}))
  }
})

test('mismatched or missing response identity cannot become playable', async () => {
  for (const attemptId of ['other-attempt', undefined]) {
    await assert.rejects(reportPlayback({token:'test', attemptId:'shown-attempt', request: async () => ({attemptId,videoUrl:'https://example.test/wrong'})}), /does not match/)
  }
})

test('revoked access never retries without the pinned identity', async () => {
  let calls = 0
  await assert.rejects(reportPlayback({token:'test', attemptId:'shown-attempt', request: async () => { calls++; throw new Error('Consent revoked') }}), /Consent revoked/)
  assert.equal(calls, 1)
})
