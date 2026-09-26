import test from 'node:test'
import assert from 'node:assert/strict'
import { watchForAppUpdate } from '../src/utils/serviceWorkerUpdate.js'

async function browser({ controlled = true, waiting = true, registrationFails = false } = {}) {
  const sw = Object.assign(new EventTarget(), { controller: controlled ? {} : null })
  const worker = Object.assign(new EventTarget(), { messages: [], postMessage(message) { this.messages.push(message) } })
  const reg = Object.assign(new EventTarget(), { waiting: waiting ? worker : null, installing: null })
  sw.register = async (path, options) => {
    assert.equal(path, '/sw.js')
    assert.equal(options.updateViaCache, 'none')
    if (registrationFails) throw new Error('offline')
    return reg
  }
  const state = { offers: [], reloads: 0, failures: 0 }
  const stop = watchForAppUpdate({ serviceWorker: sw, onReady: apply => state.offers.push(apply),
    onUnavailable: () => state.failures++, reload: () => state.reloads++ })
  await new Promise(resolve => setImmediate(resolve))
  return { sw, reg, worker, state, stop }
}

test('an already waiting release is offered, then activates only on acceptance', async () => {
  const { sw, worker, state, stop } = await browser()
  try {
    assert.equal(state.offers.length, 1)
    assert.equal(state.reloads, 0)
    assert.deepEqual(worker.messages, [])
    state.offers[0]()
    assert.deepEqual(worker.messages, [{ type: 'SKIP_WAITING' }])
    assert.equal(state.reloads, 0)
    sw.controller = {}
    sw.dispatchEvent(new Event('controllerchange'))
    assert.equal(state.reloads, 1)
  } finally { stop() }
})

test('an update installed while the tab is open is offered before activation', async () => {
  const { reg, worker, state, stop } = await browser({ waiting: false })
  try {
    reg.installing = worker
    reg.dispatchEvent(new Event('updatefound'))
    assert.equal(state.offers.length, 0)
    reg.waiting = worker
    worker.dispatchEvent(new Event('statechange'))
    assert.equal(state.offers.length, 1)
    assert.equal(state.reloads, 0)
  } finally { stop() }
})

test('first install never interrupts the first visit', async () => {
  const { sw, state, stop } = await browser({ controlled: false, waiting: false })
  try {
    sw.controller = {}
    sw.dispatchEvent(new Event('controllerchange'))
    assert.equal(state.offers.length, 0)
    assert.equal(state.reloads, 0)
  } finally { stop() }
})

test('an update accepted in another tab does not discard this tab’s unsaved form', async () => {
  const { sw, reg, state, stop } = await browser()
  try {
    reg.waiting = null
    sw.controller = {}
    sw.dispatchEvent(new Event('controllerchange'))
    assert.equal(state.reloads, 0)
    state.offers.at(-1)()
    assert.equal(state.reloads, 1)
  } finally { stop() }
})

test('unmount removes update listeners and makes an old prompt inert', async () => {
  const { sw, reg, worker, state, stop } = await browser()
  stop()
  state.offers[0]()
  sw.dispatchEvent(new Event('controllerchange'))
  reg.dispatchEvent(new Event('updatefound'))
  worker.dispatchEvent(new Event('statechange'))
  assert.equal(state.reloads, 0)
  assert.equal(state.offers.length, 1)
  assert.deepEqual(worker.messages, [])
})

test('offline registration failure is handled without a reload', async () => {
  const { state, stop } = await browser({ registrationFails: true })
  try {
    assert.equal(state.failures, 1)
    assert.equal(state.reloads, 0)
    assert.equal(state.offers.length, 0)
  } finally { stop() }
})
