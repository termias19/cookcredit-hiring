import test from 'node:test'
import assert from 'node:assert/strict'
import { workspaceDestination } from '../src/utils/workspaceDestination.js'
test('legacy settings bookmarks retain billing and invitation parameters', () => {
  assert.equal(workspaceDestination('/business/team'), '/business/profile?section=team')
  assert.equal(workspaceDestination('/business/integrations'), '/business/profile?section=integrations')
  assert.equal(workspaceDestination('/business/billing', '?checkout=success'), '/business/profile?checkout=success&section=billing')
  assert.equal(workspaceDestination('/business/shortlists'), '/business/candidates?view=saved')
})
test('application and access routes keep their exact destination', () => {
  for (const path of ['/apply/role-1', '/business/invite/opaque-token', '/owner/access']) assert.equal(workspaceDestination(path, '?invite=opaque'), path + '?invite=opaque')
})
