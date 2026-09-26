import test from 'node:test'
import assert from 'node:assert/strict'
import { rolePublicationError } from '../src/utils/rolePublicationError.js'
test('trial quota explains the limit without suggesting unavailable checkout', () => {
 const text = rolePublicationError({status:409,message:'The trial includes one open role'})
 assert.match(text,/one open trial role/); assert.match(text,/existing role/)
 assert.doesNotMatch(text,/pay|checkout|subscription/i)
})
test('permission and session failures remain distinct', () => {
 assert.match(rolePublicationError({status:401}),/Sign in again/)
 assert.match(rolePublicationError({status:403}),/permission/)
})
test('recognized field validation remains actionable', () => {
 assert.equal(rolePublicationError({status:400,message:'Pay minimum cannot exceed pay maximum'}),'Pay minimum cannot exceed pay maximum')
})
test('unknown server diagnostics are not rendered', () => {
 for (const status of [400,409,500]) assert.doesNotMatch(rolePublicationError({status,message:'private database failure'}),/private database/)
 assert.match(rolePublicationError(),/entries are still here/)
})
test('rate limiting does not masquerade as a role validation error', () => {
 assert.match(rolePublicationError({status:429}),/Wait a moment/)
})

test('early access quota explains five roles without suggesting payment', () => {
 const text = rolePublicationError({status:409,message:'Free early access includes five open roles'})
 assert.match(text,/five open roles/)
 assert.doesNotMatch(text,/pay|checkout|subscription/i)
})
