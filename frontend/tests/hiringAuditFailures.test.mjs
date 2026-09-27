import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import vm from 'node:vm'
import { transformWithEsbuild } from 'vite'

// Exercise the actual screen handlers with controlled API latency/failures.
// Child visuals are opaque; these tests do not claim to be browser acceptance.
async function screen(name, { biz, api, clipboard = async () => {}, user = { getIdToken: async () => 'test-token' }, launch = () => {}, onNavigate = () => {}, refreshProfile = async () => {}, exportName, props, extraModules = {} }) {
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
    ...extraModules,
  }
  let source = await readFile(new URL(`../src/screens/${name}.jsx`, import.meta.url), 'utf8')
  if (exportName) source += `\nexport { ${exportName} }`
  const { code } = await transformWithEsbuild(source, name + '.jsx', { loader: 'jsx', jsx: 'automatic', format: 'cjs' })
  const context = { module: { exports: {} }, require: id => modules[id] || { default: id }, navigator: { clipboard: { writeText: clipboard } }, window: { location: { origin: 'https://hiring.cookcredit.com', assign: launch } }, URLSearchParams, Set, Map }
  vm.runInNewContext(code, context)
  const Component = context.module.exports[exportName || 'default']
  function render() { index = 0; queued = []; tree = Component(props); queued.forEach(effect => effect()); return tree }
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
  assert.equal(calls, 1)
  assert.match(s.text(), /Included access/)
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


test('role trash is confirmed, restores closed, and edit uses the existing role form route', async () => {
  const changes = [], destinations = []
  const s = await screen('BusinessRoleScreen', { biz, onNavigate: path => destinations.push(path), api: {
    ...readyApi, changeBusinessRoleStatus: async ({status}) => { changes.push(status); return {role:{...role,status}} },
  } })
  await s.settle()
  s.find(p => p.children === 'Edit role').props.onClick()
  assert.deepEqual(destinations, ['/business/role/role-1/edit'])
  s.find(p => p.children === 'Move to trash').props.onClick(); s.render()
  assert.deepEqual(changes, [])
  s.find(p => p.children === 'Cancel').props.onClick(); s.render()
  assert.equal(s.find(p => p.children === 'Confirm move to trash'), undefined)
  s.find(p => p.children === 'Move to trash').props.onClick(); s.render()
  await s.find(p => p.children === 'Confirm move to trash').props.onClick(); s.render()
  assert.deepEqual(changes, ['trashed'])
  assert.equal(s.find(p => p.children === 'Edit role'), undefined)
  await s.find(p => p.children === 'Restore role (closed)').props.onClick(); s.render()
  assert.deepEqual(changes, ['trashed', 'closed'])
  assert.match(s.text(), /Reopen role/)
})

test('role list separates trash without removing records from the workspace', async () => {
  const s = await screen('BusinessRolesScreen', { biz: {...biz, roles:[role,{id:'trash-1',title:'Old role',status:'trashed'}]}, api:{} })
  assert.match(s.text(), /Cook/)
  assert.doesNotMatch(s.text(), /Old role/)
  s.find(p => p.children === 'Trash').props.onClick(); s.render()
  assert.match(s.text(), /Old role/)
  s.find(p => p.children === 'Current roles').props.onClick(); s.render()
  assert.doesNotMatch(s.text(), /Old role/)
})


test('existing role form saves only changed fields and never creates another role', async () => {
  const writes = [], destinations = []
  const original = {...role, locationLabel:'Test city', assessmentCriteria:{profileVersion:'knife-motion-v1',minimumRhythm:75}, assessmentInstructions:'Original instructions'}
  const s = await screen('BusinessRoleNewScreen', {
    exportName:'RoleForm', props:{initialRole:original},
    biz:{...biz,refresh:()=>{},addRole:()=>assert.fail('editing must not create a role')},
    onNavigate:path=>destinations.push(path),
    api:{updateBusinessRole:async request=>{writes.push(request);return {role:{...original,...request.role}}}},
    extraModules:{
      '../utils/payRangeError':{payRangeError:()=>null},
      '../utils/rolePublicationError':{rolePublicationError:error=>error?.message},
      '../data/roleRequirements':{ROLES:[],SHIFTS:[],EMPLOYMENT:[],EXPERIENCE:[],PHYSICAL:[],COOK_STATIONS:[],MAX_MUST_HAVES:5,FOOD_HANDLER_ID:'food',templateFor:()=>({skills:[]})},
    },
  })
  s.find(p=>p.value==='Cook').props.onChange({target:{value:'Senior cook'}});s.render()
  await s.find(p=>Array.isArray(p.children)&&p.children.includes('Save changes')).props.onClick()
  assert.equal(writes.length,1)
  assert.equal(JSON.stringify(writes[0].role),JSON.stringify({title:'Senior cook'}))
  assert.deepEqual(destinations,['/business/role/role-1'])
})


test('billing displays catalog amounts and limits without invented prices', async () => {
  const s = await screen('BusinessBillingScreen', { biz: { loading: false, org: {} }, api: { getBusinessBilling: async () => ({
    plan: 'trial', billingEnabled: true, checkoutConfigured: true,
    prices: [{ id: 'version', plan: 'team', interval: 'month', currency: 'usd', amount: 12345,
      limits: { seats: 7, openRoles: 9, monthlyRequests: 100 } }],
  }) } })
  await s.settle()
  assert.match(s.text(), /123.45/)
  assert.match(s.text(), /7 seats/)
  assert.match(s.text(), /9 open roles/)
  assert.doesNotMatch(s.text(), /Unlimited|\$99|\$299/)
  s.find(p => p.value === 'month' && p.onChange).props.onChange({ target: { value: 'year' } })
  s.render()
  assert.match(s.text(), /No paid plans are currently available/)
})


test('owner pricing loads on demand and saves exact cents without publishing', async () => {
  const calls = []
  const recommendation = { plan: 'team', interval: 'month', currency: 'usd', amount: 9900, limits: { seats: 5, openRoles: 5, monthlyRequests: 100 } }
  const call = async (path, options) => {
    calls.push({ path, options })
    return { prices: [], recommendations: [recommendation], stripeConfigured: false, billingEnabled: false }
  }
  const s = await screen('../components/OwnerPricing', { props: { call } })
  assert.equal(calls.length, 0)
  await s.find(p => p.onToggle).props.onToggle({ currentTarget: { open: true } }); s.render()
  assert.equal(calls.length, 1)
  s.find(p => p.onClick && JSON.stringify(p.children)?.includes('Set ')).props.onClick(); s.render()
  s.find(p => p.inputMode === 'decimal').props.onChange({ target: { value: '123.45' } }); s.render()
  await s.find(p => p.onSubmit).props.onSubmit({ preventDefault() {} }); s.render()
  const saved = calls.find(c => c.options?.method === 'POST')
  assert.equal(saved.options.body.amount, 12345)
  assert.equal(saved.options.body.previousId, null)
  assert.equal(calls.some(c => c.path.endsWith('/publish')), false)
  assert.match(s.text(), /Draft saved/)
})


test('saved view retains a shortlisted applicant before an assessment exists', async () => {
  const s = await screen('BusinessShortlistsScreen', { biz: { loading: false, shortlist: ['pending'], candidateById: () => null,
    shortlistCandidates: [{ id: 'pending', name: 'Pending Applicant', roleId: 'role-1', hasVideo: false }] } })
  assert.equal(s.find(p => p.cook?.id === 'pending').props.cook.name, 'Pending Applicant')
  assert.doesNotMatch(s.text(), /No one shortlisted yet/)
  const card = await screen('BusinessShortlistsScreen', { exportName: 'ShortlistCard', props: { cook: { id: 'pending', name: 'Pending Applicant', hasVideo: false } } })
  assert.match(card.text(), /Assessment pending/)
  assert.doesNotMatch(card.text(), /Evidence ready/)
})

test('shortlist dropdown saves privately and refreshes the workspace shortlist', async () => {
  let refreshed = 0, request
  const s = await screen('../components/EmployerApplicationReview', { exportName: 'ReviewForm',
    biz: { refresh: () => refreshed++ }, props: { canReview: true, application: { id: 'app', questions: [], review: null } },
    api: { saveEmployerReview: async args => { request = args; return { review: { status: 'shortlisted', revision: 'saved' }, employerUpdate: null } } },
  })
  s.find(p => p.value === 'reviewing' && p.onChange).props.onChange({ target: { value: 'shortlisted' } }); s.render()
  assert.match(s.text(), /Save private review to apply/)
  await s.find(p => p.children === 'Save private review').props.onClick(); s.render()
  assert.equal(request.review.status, 'shortlisted')
  assert.equal(request.review.publish, false)
  assert.equal(refreshed, 1)
  assert.match(s.text(), /Private review saved/)
})
