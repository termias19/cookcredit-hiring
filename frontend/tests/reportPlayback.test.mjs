import test from 'node:test'
import assert from 'node:assert/strict'
import { reportPlayback, recordingLabel, playbackFailure } from '../src/utils/reportPlayback.js'

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

test('missing and expired recordings explain availability without deleting the assessment', () => {
  for (const code of ['recording_expired','recording_missing']) {
    const failure = playbackFailure({code,requestId:'a'.repeat(32),message:'secret URL'})
    assert.equal(failure.terminal,true)
    assert.match(failure.message,/application and assessment history remain available/)
    assert.match(failure.message,/Reference: a{32}/)
    assert.ok(!failure.message.includes('secret'))
  }
  assert.equal(playbackFailure({code:'recording_temporarily_unavailable'}).terminal,false)
  assert.equal(recordingLabel(), 'Check recording')
  assert.equal(recordingLabel({state:'expired'}), 'Recording expired')
  assert.equal(recordingLabel({state:'unavailable'}), 'Recording unavailable')
})
