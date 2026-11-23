import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import vm from 'node:vm'
import { transformWithEsbuild } from 'vite'
import { reportPlayback } from '../src/utils/reportPlayback.js'

async function compiled(path, modules, globals = {}) {
  const source = await readFile(new URL(path, import.meta.url), 'utf8')
  const { code } = await transformWithEsbuild(source, path, { loader: path.endsWith('jsx') ? 'jsx' : 'js', jsx: 'automatic', format: 'cjs', define: { 'import.meta.env': '{}' } })
  const context = { module: { exports: {} }, require: name => {
    const value = modules[name] || {}
    return 'default' in value ? { __esModule: true, ...value } : value
  }, AbortController, DOMException, setTimeout, clearTimeout, ...globals }
  vm.runInNewContext(code, context)
  return context.module.exports
}

test('cancelling an obsolete request stops the fetch without an error report', async () => {
  const reports = [], fetched = []
  const { http } = await compiled('../src/utils/http.js', {
    './errorReporting.js': { reportClientError: code => reports.push(code) },
    './errorReference.js': { errorReference: () => '' }, '../config': { PREVIEW: false },
  }, { fetch: (_, options) => new Promise((resolve, reject) => {
    fetched.push(options)
    options.signal.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))
  }) })
  const controller = new AbortController()
  const pending = http('/private', { signal: controller.signal })
  await new Promise(resolve => setImmediate(resolve))
  controller.abort()
  await assert.rejects(pending, { name: 'AbortError' })
  assert.equal(fetched.length, 1); assert.equal(fetched[0].signal.aborted, true)
  await assert.rejects(http('/private', { signal: controller.signal }), { name: 'AbortError' })
  assert.equal(fetched.length, 1); assert.deepEqual(reports, [])
  await assert.rejects(http('/private', { timeoutMs: 1 }), /timed out/)
  assert.deepEqual(reports, ['api_timeout'])
})

test('the displayed-attempt binding forwards cancellation to playback', async () => {
  const controller = new AbortController()
  const result = await reportPlayback({ token: 'controlled', attemptId: 'selected', signal: controller.signal,
    request: async options => { assert.equal(options.signal, controller.signal); assert.equal(options.attemptId, 'selected'); return { attemptId: 'selected', videoUrl: 'private' } } })
  assert.equal(result, 'private')
})

const jsx = (type, props) => ({ type, props })
function nodes(value) {
  if (Array.isArray(value)) return value.flatMap(nodes)
  if (!value || typeof value !== 'object') return []
  return [value, ...nodes(value.props?.children)]
}

test('a long reel feed mounts a video only for the visible candidate', async () => {
  let values = []
  const Player = () => null
  const react = { useRef: () => ({ current: {} }), useEffect: () => {}, useState: initial => [values.length ? values.shift() : initial, () => {}] }
  const { default: Feed } = await compiled('../src/components/MobileCandidateFeed.jsx', {
    react, 'react/jsx-runtime': { jsx, jsxs: jsx }, 'react-router-dom': { useNavigate: () => () => {} },
    '../context/AuthContext': { useAuth: () => ({ user: {} }) },
    '../context/BusinessContext': { useBusiness: () => ({ isShortlisted: () => false }) },
    '../hooks/usePlaybackView': { default: () => [false, () => {}] },
    './CandidateVideoPlayer': { default: Player }, '../config': { PREVIEW: false },
  })
  const candidates = Array.from({ length: 200 }, (_, index) => ({ id: String(index) }))
  const entries = nodes(Feed({ candidates })).filter(node => typeof node.type === 'function')
  const reels = entries.filter(node => node.props?.candidate)
  assert.equal(reels.length, 200)
  for (const active of [0, 100, 199]) {
    let players = 0
    for (let index = 0; index < reels.length; index++) {
      values = [index === active, { assessment: { attemptId: String(index) } }, 'cached-private-url', '', 0, false, false, '', false]
      players += nodes(reels[index].type(reels[index].props)).filter(node => node.type === Player).length
    }
    assert.equal(players, 1)
  }
})

test('player cleanup releases buffered media and restores a changed source on setup', async () => {
  const effects = [], calls = []
  let src = 'first'
  const element = { getAttribute: () => src, setAttribute: (_, value) => { src = value },
    pause: () => calls.push('pause'), removeAttribute: () => { src = null; calls.push('remove') }, load: () => calls.push('load') }
  const { default: Player } = await compiled('../src/components/CandidateVideoPlayer.jsx', {
    react: { useRef: () => ({ current: element }), useState: initial => [initial, () => {}], useEffect: fn => effects.push(fn) },
    'react/jsx-runtime': { jsx, jsxs: jsx }, '../hooks/usePlaybackView': { default: () => [false] },
  })
  Player({ url: 'first' }); const cleanup = effects[0]()
  src = 'second'; cleanup()
  assert.deepEqual(calls, ['pause', 'remove', 'load']); assert.equal(src, null)
  effects.length = 0; Player({ url: 'second' }); effects[0]()
  assert.equal(src, 'second'); assert.equal(calls.at(-1), 'load')
})
