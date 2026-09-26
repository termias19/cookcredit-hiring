import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

test('hosting permits signed hiring recordings without allowing arbitrary remote media', () => {
  const config = JSON.parse(readFileSync(new URL('../firebase.json', import.meta.url), 'utf8'))
  const policies = config.hosting.headers.flatMap(rule => rule.headers.filter(h => h.key === 'Content-Security-Policy').map(h => ({...h,source:rule.source})))
  assert.ok(policies.length > 0)
  for (const policy of policies) {
    const media = policy.value.split(';').map(s => s.trim()).find(s => s.startsWith('media-src ')).split(/\s+/).slice(1)
    const bucket = policy.source === '/landing/assessment/**' ? 'foodnlit-1123e.firebasestorage.app' : 'cookcredit-hiring-stg-media-915097816203'
    const recording = new URL(`https://storage.googleapis.com/${bucket}/recording.mp4?X-Goog-Signature=test`)
    assert.ok(media.includes(recording.origin + '/' + recording.pathname.split('/')[1] + '/'))
    assert.ok(!media.includes('*') && !media.includes('https:') && !media.includes('https://storage.googleapis.com') && !media.includes('https://firebasestorage.googleapis.com'))
  }
})
