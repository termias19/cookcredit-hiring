import test from 'node:test'
import assert from 'node:assert/strict'
import { saveHiringCv } from '../src/utils/saveHiringCv.js'

test('CV save requests a destination before loading and confirms only after close', async () => {
  const order = []
  const browser = { showSaveFilePicker: async () => { order.push('picker'); return { createWritable: async () => ({ write: async b => { assert.equal(b, 'pdf'); order.push('write') }, close: async () => order.push('close') }) } } }
  assert.equal(await saveHiringCv(async () => { order.push('load'); return 'pdf' }, browser, {}, {}), 'saved')
  assert.deepEqual(order, ['picker', 'load', 'write', 'close'])
})

test('cancelled save does not fetch the private CV', async () => {
  const browser = { showSaveFilePicker: async () => { throw Object.assign(Error('cancelled'), { name: 'AbortError' }) } }
  assert.equal(await saveHiringCv(() => assert.fail('unexpected fetch'), browser, {}, {}), 'cancelled')
})

test('failed write aborts and never reports saved', async () => {
  let aborted = false
  const browser = { showSaveFilePicker: async () => ({ createWritable: async () => ({ write: async () => { throw Error('disk full') }, abort: async () => { aborted = true } }) }) }
  await assert.rejects(saveHiringCv(async () => 'pdf', browser, {}, {}), /disk full/)
  assert.equal(aborted, true)
})

for (const blocked of [false, true]) test(`download fallback is only a request, picker blocked: ${blocked}`, async () => {
  const calls = [], timers = []
  const link = { click: () => calls.push('click'), remove: () => calls.push('remove') }
  const browser = { setTimeout: (fn, delay) => timers.push({ fn, delay }) }
  if (blocked) browser.showSaveFilePicker = async () => { throw Object.assign(Error('embedded'), { name: 'SecurityError' }) }
  const doc = { createElement: () => link, body: { appendChild: () => calls.push('append') } }
  const urls = { createObjectURL: () => 'blob:test', revokeObjectURL: value => calls.push(value) }
  assert.equal(await saveHiringCv(async () => 'pdf', browser, doc, urls), 'requested')
  assert.equal(link.download, 'candidate-cv.pdf')
  assert.deepEqual(calls, ['append', 'click', 'remove'])
  assert.equal(timers[0].delay, 60000)
  timers[0].fn()
  assert.equal(calls.at(-1), 'blob:test')
})
