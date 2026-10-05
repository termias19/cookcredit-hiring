import test from 'node:test'
import assert from 'node:assert/strict'
import { shareableRoles, selectedShareableRole } from '../src/utils/shareableRoles.js'

test('integration sharing excludes closed, trashed, draft and unknown roles', () => {
  const roles = ['open', 'closed', 'trashed', 'draft', undefined].map((status, id) => ({ id: String(id), status }))
  assert.deepEqual(shareableRoles(roles).map(role => role.id), ['0'])
  assert.equal(selectedShareableRole(roles, '2'), '0')
})

test('closing the selected role immediately invalidates its sharing selection', () => {
  const roles = [{ id: 'first', status: 'open' }, { id: 'selected', status: 'open' }]
  assert.equal(selectedShareableRole(roles, 'selected'), 'selected')
  roles[1].status = 'closed'
  assert.equal(selectedShareableRole(roles, 'selected'), 'first')
  roles[0].status = 'trashed'
  assert.equal(selectedShareableRole(roles, 'selected'), '')
  assert.equal(selectedShareableRole(undefined, 'selected'), '')
})
