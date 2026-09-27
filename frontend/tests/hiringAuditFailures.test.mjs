import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import vm from 'node:vm'
import { transformWithEsbuild } from 'vite'

// Exercise the actual screen handlers with controlled API latency/failures.
// Child visuals are opaque; these tests do not claim to be browser acceptance.
async function screen(name, { biz, api, clipboard = async () => {}, user = { getIdToken: async () => 'test-token' }, launch = () => {}, onNavigate = () => {}, refreshProfile = async () => {} }) {
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
  const navigate = onNavigate, searchParams = new URLSearchParams()
  const modules = {
    react, 'react/jsx-runtime': { jsx, jsxs: jsx, Fragment: 'fragment' },
    'react-router-dom': { useNavigate: () => navigate, useLocation: () => ({ pathname: '/apply/role-1' }), useParams: () => ({ id: 'role-1', roleId: 'role-1' }), useSearchParams: () => [searchParams] },
    'framer-motion': { motion: new Proxy({}, { get: (_, key) => key }), AnimatePresence: 'presence' },
    '../context/BusinessContext': { useBusiness: () => biz },
    '../context/AuthContext': { useAuth: () => ({ user, refreshProfile }) },
    '../utils/Api': api,
    '../data/culinaryTaxonomy': { labelOf: id => id },
    '../styles/motion': { staggerContainer: () => ({}) },
  }
  const source = await readFile(new URL(`../src/screens/${name}.jsx`, import.meta.url), 'utf8')
  const { code } = await transformWithEsbuild(source, name + '.jsx', { loader: 'jsx', jsx: 'automatic', format: 'cjs' })
  const context = { module: { exports: {} }, require: id => modules[id] || { default: id }, navigator: { clipboard: { writeText: clipboard } }, window: { location: { origin: 'https://hiring.cookcredit.com', assign: launch } }, URLSearchParams, Set, Map }
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

const applicant = { emailVerified: true, getIdToken: async () => 'test-token' }
const applicantApi = {
  getHiringRole: async () => ({ role: { id: 'role-1', company: { name: 'Employer' }, questions: [], consentText: 'Sharing notice' } }),
  getMyHiringApplication: async () => ({ application: null }),
}
async function completeDetails(s) {
  await s.settle()
  s.find(p => p.id === 'application-name').props.onChange({ target: { value: 'Applicant' } })
  s.find(p => p.type === 'checkbox').props.onChange({ target: { checked: true } })
  s.render()
}
test('one applicant action saves once and opens the returned assessment URL', async () => {
  const calls = [], launches = []
  const s = await screen('HiringApplicationScreen', { user: applicant, launch: url => launches.push(url), api: {
    ...applicantApi,
    applyToHiringRole: async () => { calls.push('save'); return { application: { id: 'saved-1' } } },
    startHiringAttempt: async ({ applicationId }) => { calls.push(applicationId); return { launchUrl: 'https://hiring.cookcredit.com/landing/assessment/?hiringSession=opaque' } },
  } })
  await s.settle()
  assert.equal(s.find(p => p.children === 'Continue to assessment').props.disabled, true)
  await completeDetails(s)
  await s.find(p => p.children === 'Continue to assessment').props.onClick()
  assert.deepEqual(calls, ['save', 'saved-1'])
  assert.deepEqual(launches, ['https://hiring.cookcredit.com/landing/assessment/?hiringSession=opaque'])
})
test('assessment entry failure retains the saved application for retry', async () => {
  let saves = 0
  const s = await screen('HiringApplicationScreen', { user: applicant, api: {
    ...applicantApi, applyToHiringRole: async () => { saves++; return { application: { id: 'saved-2' } } },
    startHiringAttempt: async () => { throw Error('offline') },
  } })
  await completeDetails(s)
  await s.find(p => p.children === 'Continue to assessment').props.onClick(); s.render()
  assert.equal(saves, 1)
  const detail = s.find(p => p.applicationId === 'saved-2')
  assert.match(detail.props.entryError, /Your details are saved/)
  assert.match(detail.props.entryError, /retry/)
})
test('existing applications resume in place without creating another application or attempt', async () => {
  const s = await screen('HiringApplicationScreen', { user: applicant, api: {
    ...applicantApi, getMyHiringApplication: async () => ({ application: { id: 'existing' } }),
    applyToHiringRole: () => assert.fail('must not apply again'), startHiringAttempt: () => assert.fail('must not start automatically'),
  } })
  await s.settle()
  assert.ok(s.find(p => p.applicationId === 'existing'))
})
test('assessment return resolves the server-owned application with replacement navigation', async () => {
  const destinations = []
  const s = await screen('HiringAssessmentReturnScreen', { user: applicant, onNavigate: (...args) => destinations.push(args), api: {
    getHiringAssessmentSession: async () => ({ session: { applicationId: 'submitted-1', status: 'processing' } }),
  } })
  await s.settle()
  assert.equal(destinations[0][0], '/application/submitted-1')
  assert.equal(destinations[0][1].replace, true)
})


test('team load failures expose a retry and recover', async () => {
  let fail = true
  const s = await screen('BusinessTeamScreen', { biz: { ...biz, org: { plan: 'team' } }, api: {
    getBusinessTeam: async () => { if (fail) throw Error('offline'); return { members: [], invitations: [], canManage: true } },
  } })
  await s.settle()
  assert.match(s.text(), /offline/)
  fail = false
  await s.find(p => p.children === 'Retry loading team').props.onClick()
  s.render()
  assert.doesNotMatch(s.text(), /offline/)
  assert.match(s.text(), /Invite a teammate/)
})

test('included hiring access never offers an invitation the backend will reject', async () => {
  const s = await screen('BusinessTeamScreen', { biz: { ...biz, org: { plan: 'trial', integrationAccess: { earlyAccess: true } } }, api: {
    getBusinessTeam: async () => ({ members: [], invitations: [], canManage: true }),
  } })
  await s.settle()
  assert.match(s.text(), /Team invitations are not enabled/)
  assert.equal(s.find(p => p['aria-label'] === 'Teammate email'), undefined)
})

test('invitation mail acceptance is not claimed as inbox delivery; failed copy retains selectable link', async () => {
  const s = await screen('BusinessTeamScreen', { biz: { ...biz, org: { plan: 'team' } }, clipboard: async () => { throw Error('denied') }, api: {
    getBusinessTeam: async () => ({ members: [], invitations: [], canManage: true }),
    inviteBusinessTeamMember: async () => ({ invitation: { emailDelivered: true, inviteUrl: 'https://hiring.cookcredit.com/business/invite/test-only' } }),
  } })
  await s.settle()
  s.find(p => p['aria-label'] === 'Teammate email').props.onChange({ target: { value: 'controlled@example.test' } })
  s.render(); await s.settle()
  await s.find(p => p.onClick && JSON.stringify(p.children)?.includes('Create invitation')).props.onClick()
  s.render()
  assert.match(s.text(), /Inbox receipt is not confirmed/)
  assert.doesNotMatch(s.text(), /Email delivered/)
  await s.find(p => p.onClick && JSON.stringify(p.children)?.includes('Copy invitation link')).props.onClick()
  s.render()
  assert.match(s.text(), /Could not copy automatically/)
  assert.equal(s.find(p => p['aria-label'] === 'Invitation link').props.value, 'https://hiring.cookcredit.com/business/invite/test-only')
})


test('server included-team entitlement enables invitations without inventing a paid plan', async () => {
  const s = await screen('BusinessTeamScreen', { biz: { ...biz, org: {plan:'trial'} }, api: {
    getBusinessTeam: async () => ({members:[], invitations:[], canManage:true, invitationAccess:{enabled:true,seatLimit:5}}),
  } })
  await s.settle()
  assert.match(s.text(), /5 seats include members and pending invitations/)
  assert.ok(s.find(p => p['aria-label'] === 'Teammate email'))
})

test('opening a team invitation never accepts it until the user acts', async () => {
  let accepts=0, redirects=0
  const s = await screen('BusinessInviteAcceptScreen', { api: {acceptBusinessTeamInvitation: async () => {accepts++}}, onNavigate:()=>{redirects++} })
  await s.settle()
  assert.equal(accepts,0)
  await s.find(p => p.children === 'Accept invitation').props.onClick()
  assert.equal(accepts,1)
  assert.equal(redirects,1)
})
