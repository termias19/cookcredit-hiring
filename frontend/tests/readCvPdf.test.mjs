import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import vm from 'node:vm'
import { transformWithEsbuild } from 'vite'

async function reader(pdf, { timeout = false } = {}) {
  let destroyed = 0, options
  const task = { promise: Promise.resolve(pdf), destroy: async () => { destroyed++ } }
  const source = await readFile(new URL('../src/utils/readCvPdf.js', import.meta.url), 'utf8')
  const { code } = await transformWithEsbuild(source, 'reader.js', { format: 'cjs' })
  const ctx = { module: { exports: {} }, Uint8Array, DOMException, setTimeout: timeout ? fn => setTimeout(fn, 1) : setTimeout, clearTimeout,
    require: name => name === 'pdfjs-dist' ? { GlobalWorkerOptions: {}, getDocument: input => { options = input; return task } } : { default: '/local-worker.mjs' } }
  vm.runInNewContext(code, ctx)
  return { read: ctx.module.exports.readCvPdf, destroyed: () => destroyed, options: () => options }
}
const blob = new Blob(['synthetic PDF'])

test('extracts plain text and destroys the worker without enabling eval or remote assets', async () => {
  let cleaned = false
  const r = await reader({ numPages: 1, getPage: async () => ({ getTextContent: async () => ({ items: [{str:'Cook',hasEOL:true},{str:'Experience'}] }), cleanup: () => { cleaned = true } }) })
  const pages = await r.read(blob)
  assert.equal(pages[0].text, 'Cook\nExperience')
  assert.equal(r.options().isEvalSupported, false)
  assert.equal(r.options().useWorkerFetch, false)
  assert.equal(r.destroyed(), 1)
  assert.equal(cleaned, true)
})

test('scanned PDFs explain the original-file fallback', async () => {
  const r = await reader({ numPages: 1, getPage: async () => ({ getTextContent: async () => ({items:[]}), cleanup() {} }) })
  await assert.rejects(r.read(blob), /scanned CV/)
  assert.equal(r.destroyed(), 1)
})

test('page and byte limits stop excessive extraction', async () => {
  const r = await reader({numPages:31})
  await assert.rejects(r.read(blob), /30 pages/)
  assert.equal(r.destroyed(), 1)
  await assert.rejects(r.read({size:3*1024*1024}), /too large/)
})

test('timeout destroys a stalled parsing task', async () => {
  const r = await reader(new Promise(() => {}), {timeout:true})
  await assert.rejects(r.read(blob), /too long/)
  assert.equal(r.destroyed(), 1)
})

test('closing the reader aborts parsing and destroys its worker', async () => {
  const r = await reader(new Promise(() => {}))
  const controller = new AbortController()
  const result = r.read(blob, {signal:controller.signal})
  await new Promise(resolve => setImmediate(resolve))
  controller.abort()
  await assert.rejects(result, error => error.name === 'AbortError')
  assert.equal(r.destroyed(), 1)
})
