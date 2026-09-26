import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import vm from 'node:vm'
import { transformWithEsbuild } from 'vite'

// Exercise the actual screen handlers with controlled API latency/failures.
// Child visuals are opaque; these tests do not claim to be browser acceptance.
async function screen(name, { biz, api, clipboard = async () => {}, user = { getIdToken: async () => 'test-token' } }) {
  const state = [], effects = [], refs = []
  let index, queued = [], tree
  const react = {
    useState(initial) {
      const slot = index++
      if (!(slot in state)) state[slot] = typeof initial === 'function' ? initial() : initial
      return [state[slot], next => { state[slot] = typeof next === 'function' ? next(state[slot]) : next }]
    },
    useRef(initial) { const slot = index++; return refs[slot] ||= { current: initial } },
    useCallback(fn) { index++; return fn },
    useMemo(fn) { index++; return fn() },
    useEffect(fn, deps) {
      const slot = index++, old = effects[slot]
      if (!old || deps.some((dep, i) => !Object.is(dep, old.deps[i]))) {
        queued.push(() => { old?.cleanup?.(); effects[slot] = { deps, cleanup: fn() } })
      }
    },
  }
  const jsx = (type, props) => ({ type, props })
  const navigate = () => {}, searchParams = new URLSearchParams()
  const modules = {
    react, 'react/jsx-runtime': { jsx, jsxs: jsx, Fragment: 'fragment' },
    'react-router-dom': { useNavigate: () => navigate, useLocation: () => ({ pathname: '/apply/role-1' }), useParams: () => ({ id: 'role-1', roleId: 'role-1' }), useSearchParams: () => [searchParams] },
    'framer-motion': { motion: new Proxy({}, { get: (_, key) => key }), AnimatePresence: 'presence' },
    '../context/BusinessContext': { useBusiness: () => biz },
    '../context/AuthContext': { useAuth: () => ({ user }) },
    '../utils/Api': api,
    '../data/culinaryTaxonomy': { labelOf: id => id },
    '../styles/motion': { staggerContainer: () => ({}) },
  }
  const source = await readFile(new URL(`../src/screens/${name}.jsx`, import.meta.url), 'utf8')
  const { code } = await transformWithEsbuild(source, name + '.jsx', { loader: 'jsx', jsx: 'automatic', format: 'cjs' })
  const context = { module: { exports: {} }, require: id => modules[id] || { default: id }, navigator: { clipboard: { writeText: clipboard } }, window: { location: { origin: 'https://hiring.cookcredit.com' } }, URLSearchParams, Set, Map }
  vm.runInNewContext(code, context)
  const Component = context.module.exports.default
  function render() { index = 0; queued = []; tree = Component(); queued.forEach(effect => effect()); return tree }
  function nodes(node) {
    if (node == null || node === false) return []
    if (Array.isArray(node)) return node.flatMap(nodes)
    return [node, ...nodes(node.props?.children)]
  }
  const text = () => nodes(tree).filter(node => typeof node === 'string' || typeof node === 'number').join(' ')
  const find = predicate => nodes(tree).find(node => node?.props && predicate(node.props, node))
  async function settle() { await new Promise(resolve => setImmediate(resolve)); render() }
  render()
  return { render, settle, text, find }
}
const role = { id: 'role-1', title: 'Cook', status: 'open' }
const biz = { getToken: async () => 'test-token', roleById: () => role, candidateById: () => null, isShortlisted: () => false }
const readyApi = { getBusinessRole: async () => ({ role, pipeline: [] }), getHiringApplications: async () => ({ applications: [], page: {} }) }

test('clipboard rejection never reports success and provides the actual role link', async () => {
  const s = await screen('BusinessRoleScreen', { biz, api: readyApi, clipboard: async () => { throw new Error('denied') } })
  await s.settle()
  await s.find(p => p.onClick && JSON.stringify(p.children)?.includes('Copy application link')).props.onClick()
  s.render()
  assert.match(s.text(), /Could not copy automatically/)
  assert.doesNotMatch(s.text(), /Application link copied/)
  assert.equal(s.find(p => p['aria-label'] === 'Application link').props.value, 'https://hiring.cookcredit.com/apply/role-1')
})
test('a failed initial application read shows retry rather than an empty pipeline', async () => {
  let fail = true
  const s = await screen('BusinessRoleScreen', { biz, api: { ...readyApi, getHiringApplications: async () => { if (fail) throw Error('offline'); return { applications: [] } } } })
  await s.settle()
  assert.match(s.text(), /Applications could not be loaded/)
  assert.doesNotMatch(s.text(), /No candidates yet/)
  fail = false
  s.find(p => p.children === 'Retry').props.onClick()
  s.render(); await s.settle()
  assert.doesNotMatch(s.text(), /Applications could not be loaded/)
  assert.match(s.text(), /No candidates yet/)
})
test('late pagination cannot add applicants from a previous filter', async () => {
  let resolvePage
  const s = await screen('BusinessRoleScreen', { biz, api: { ...readyApi, getHiringApplications: async request => {
    if (request.cursor) return new Promise(resolve => { resolvePage = resolve })
    return { applications: [], page: { nextCursor: request.city ? null : 'next-page' } }
  } } })
  await s.settle()
  const pending = s.find(p => p.children === 'Load more applications').props.onClick()
  await new Promise(resolve => setImmediate(resolve))
  s.find(p => p['aria-label'] === 'Filter by applicant city').props.onChange({ target: { value: 'Atlanta' } })
  s.render(); await s.settle()
  resolvePage({ applications: [{ id: 'stale', candidate: { id: 'stale', name: 'Stale Applicant' } }], page: {} })
  await pending; s.render()
  assert.doesNotMatch(s.text(), /Stale Applicant/)
  assert.match(s.text(), /No applications match these filters/)
})
test('pagination errors remain recoverable without discarding the current page', async () => {
  let fail = true
  const s = await screen('BusinessRoleScreen', { biz, api: { ...readyApi, getHiringApplications: async request => {
    if (request.cursor && fail) throw Error('offline')
    return { applications: [], page: { nextCursor: request.cursor ? null : 'next-page' } }
  } } })
  await s.settle()
  await s.find(p => p.children === 'Load more applications').props.onClick(); s.render()
  assert.match(s.text(), /More applications could not be loaded/)
  fail = false
  await s.find(p => p.children === 'Load more applications').props.onClick(); s.render()
  assert.doesNotMatch(s.text(), /More applications could not be loaded/)
})
test('billing waits for workspace access before offering plans or calling billing', async () => {
  let calls = 0
  const workspace = { loading: true, org: null }
  const s = await screen('BusinessBillingScreen', { biz: workspace, api: { getBusinessBilling: async () => { calls++; return {} } } })
  assert.match(s.text(), /Loading workspace access/)
  assert.doesNotMatch(s.text(), /\$99|14 days|Contact sales/)
  workspace.loading = false
  s.render()
  assert.match(s.text(), /Workspace access could not be loaded/)
  workspace.org = { integrationAccess: { earlyAccess: true } }
  s.render(); await s.settle()
  assert.equal(calls, 0)
  assert.match(s.text(), /Free early access/)
  assert.doesNotMatch(s.text(), /\$99|14 days|Contact sales/)
})

test('applicant connection failure offers a retry that returns to the same role', async () => {
  let calls = 0
  const s = await screen('HiringApplicationScreen', { user: null, api: { getHiringRole: async request => {
    assert.equal(request.roleId, 'role-1')
    if (++calls === 1) throw new TypeError('Failed to fetch')
    return { role: { id: 'role-1', title: 'Cook', company: { name: 'Employer' }, questions: [] } }
  } } })
  await s.settle()
  assert.match(s.text(), /Could not connect to CookCredit/)
  s.find(p => p.children === 'Retry').props.onClick()
  s.render(); await s.settle()
  assert.match(s.text(), /Apply with CookCredit/)
  assert.doesNotMatch(s.text(), /Could not connect/)
  assert.equal(calls, 2)
})
