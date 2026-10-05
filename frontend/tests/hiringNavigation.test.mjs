import test from 'node:test'
import assert from 'node:assert/strict'
import { homeFor, safeAuthDestination, rememberDestination, rememberAccountDestination, pendingDest, clearPendingDestination, authDestination, signupDestination } from '../src/utils/homeFor.js'
import { NODES, scanText } from '../src/data/culinaryTaxonomy.js'
import { initialSignupRole, authEntryDestination, authEntryLink } from '../src/utils/homeFor.js'

test('all assessment entry routes select applicant signup, including sharing and standalone assessment', () => {
  for (const dest of ['/assessment', '/assessment-sharing/cook/attempt', '/application-assessment-return/session', '/apply/role?invite=opaque']) {
    assert.equal(initialSignupRole(dest), 'cook')
    assert.equal(signupDestination(initialSignupRole(dest), dest), dest)
  }
  assert.equal(initialSignupRole('/business/roles', 'cook'), 'eat')
  assert.equal(initialSignupRole('/business/invite/token'), 'eat')
  assert.equal(initialSignupRole(null, 'cook'), 'cook')
})

function storage() {
  const values = new Map()
  return { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value), removeItem: key => values.delete(key) }
}
globalThis.sessionStorage = storage()
globalThis.localStorage = storage()

test('only server-granted company members land in the workspace', () => {
  assert.equal(homeFor({ roles: ['business'], employerAccessAllowed: true }), '/business/roles')
  assert.equal(homeFor({ roles: ['eater'], activeRole: 'business', employerAccessAllowed: true }), '/business/onboarding')
  assert.equal(homeFor({ roles: ['eater'], activeRole: 'business' }), '/business/onboarding')
  assert.equal(homeFor({ roles: ['cook'], activeRole: 'cook' }), '/applications')
  assert.equal(homeFor(null), '/applications')
})
test('invitation query survives repeated guards, verification and arrival', () => {
  const from = { pathname: '/apply/role-123', search: '?invite=cci_example', hash: '#assessment' }
  const dest = rememberDestination(from)
  assert.equal(dest, '/apply/role-123?invite=cci_example#assessment')
  for (let render = 0; render < 3; render++) assert.equal(authDestination({ roles: ['business'] }), dest)
  clearPendingDestination('/verify')
  assert.equal(pendingDest(), dest)
  clearPendingDestination(dest)
  assert.equal(pendingDest(), null)
})
test('untrusted redirects and retired identity/service routes cannot re-enter the app', () => {
  for (const value of ['https://evil.example', '//evil.example', '/\\evil.example', '/profile/../../login', '/login', '/verify', '/skill', '/browse', '/onboarding/bio', '/cook/someone', '/profile%2f..%2fskill']) {
    assert.equal(safeAuthDestination(value), null, value)
  }
  localStorage.setItem('cc_pending_onboarding', '1')
  sessionStorage.setItem('postAuthDest', '/onboarding/bio')
  assert.equal(authDestination({ roles: ['cook'] }), '/applications')
  clearPendingDestination()
  assert.equal(localStorage.getItem('cc_pending_onboarding'), null)
})

test('employer intent reaches the approval guard instead of the applicant dashboard', () => {
  for (const target of ['/business/roles', '/business/onboarding', '/business/candidates']) {
    rememberDestination(target)
    assert.equal(authDestination({ id: 'candidate', roles: ['eater'], employerAccessAllowed: false }), target)
  }
  assert.equal(authDestination({ id: 'candidate' }, '/owner/access'), '/applications')
  clearPendingDestination()
})

test('explicit signup choice beats an old dashboard destination and preserves invitations', () => {
  assert.equal(signupDestination('eat', '/applications'), '/business/onboarding')
  assert.equal(signupDestination('eat', '/profile'), '/business/onboarding')
  assert.equal(signupDestination('cook', '/business/roles'), '/applications')
  assert.equal(signupDestination('cook', '/apply/role-123?invite=opaque'), '/apply/role-123?invite=opaque')
  assert.equal(signupDestination('eat', '/business/invite/opaque'), '/business/invite/opaque')
  assert.equal(signupDestination('eat', '//evil.example'), '/business/onboarding')
})

test('a verification tab restores only its account-bound applicant destination', () => {
  rememberAccountDestination('candidate', '/apply/role-123?invite=cci_example')
  assert.equal(authDestination({ id: 'candidate' }), '/apply/role-123?invite=cci_example')
  assert.equal(authDestination({ id: 'other' }), '/applications')
  clearPendingDestination('/apply/role-123?invite=cci_example')
  assert.equal(authDestination({ id: 'candidate' }), '/applications')
})
test('an explicit new invitation wins over old session intent; signout clears intent', () => {
  rememberDestination('/business/roles')
  assert.equal(authDestination({}, '/business/invite/accepted-token'), '/business/invite/accepted-token')
  rememberDestination('/application-assessment-return/session-123')
  assert.equal(pendingDest(), '/application-assessment-return/session-123')
  clearPendingDestination()
  assert.equal(pendingDest(), null)
})

test('existing applicant login preserves the invitation in a new verification tab', () => {
  const invitation = '/apply/role-123?invite=cci_example'
  rememberDestination(invitation)
  rememberAccountDestination('candidate', authDestination(null))
  sessionStorage = storage() // Email link opens a fresh tab on the same browser.
  clearPendingDestination('/account/action')
  assert.equal(authDestination(null, undefined, 'candidate'), invitation)
  assert.equal(authDestination(null, undefined, 'another-account'), '/applications')
  assert.equal(authDestination({ id: 'candidate' }), invitation)
  assert.equal(authDestination({ id: 'another-account' }), '/applications')
  clearPendingDestination()
})

test('account switch retains only the explicitly requested validated invitation', () => {
  const from = safeAuthDestination({pathname:'/apply/role-456',search:'?invite=cci_next'})
  rememberAccountDestination('previous-account', '/business/roles')
  clearPendingDestination() // Existing sign-out clears account-bound state.
  rememberDestination(from)
  assert.equal(authDestination({id:'new-applicant'}), from)
  assert.equal(localStorage.getItem('cc_account_destination'), null)
  clearPendingDestination()
})
test('culinary evidence retains its meaning instead of inherited domestic-service labels', () => {
  const lookup = Object.fromEntries(NODES.map(node => [node.id, node]))
  assert.equal(lookup.food_safety_cert.label, 'Food-safety certification')
  assert.equal(lookup.prep_cook.label, 'Prep cook')
  assert.equal(lookup.servsafe_manager.label, 'ServSafe Manager')
  assert.ok(scanText('Prep cook with knife skills and julienne.').some(item => item.canonical_id === 'knife_skills'))
  assert.ok(!NODES.some(node => /household|pet care|nanny|caregiv|background check/i.test(node.label)))
})


test('role editor survives authentication without allowing arbitrary nested redirects', () => {
  assert.equal(safeAuthDestination('/business/role/role-1/edit'), '/business/role/role-1/edit')
  assert.equal(safeAuthDestination('/business/role/role-1/edit/elsewhere'), null)
})


test('copied employer links override stale applicant state through login and signup', () => {
  rememberDestination('/apply/old-role')
  const dest = authEntryDestination({ search: '?next=/business/roles', state: { from: '/applications' } })
  assert.equal(dest, '/business/roles')
  const signup = authEntryLink('/signup', dest)
  assert.equal(authEntryDestination({ search: new URL(signup, 'https://hiring.example').search }), dest)
  assert.equal(initialSignupRole(dest), 'eat')
  assert.equal(authDestination({ roles: ['eater'] }, dest), '/business/roles')
  clearPendingDestination()
})

test('approved employer skips setup but keeps team invitations and applicant links', () => {
  const manager = { id: 'manager', roles: ['business'], employerAccessAllowed: true }
  for (const dest of ['/business/onboarding', '/business/onboarding?source=invite']) assert.equal(authDestination(manager, dest), '/business/roles')
  for (const dest of ['/business/invite/token', '/apply/role?invite=token', '/assessment']) {
    assert.equal(authDestination(manager, dest), dest)
    assert.equal(authEntryDestination({ search: new URL(authEntryLink('/login', dest), 'https://hiring.example').search }), dest)
  }
  assert.equal(authDestination({ roles: ['eater'], employerAccessAllowed: true }, '/business/onboarding'), '/business/onboarding')
  assert.equal(authEntryLink('/login', 'https://untrusted.example'), '/login')
})
