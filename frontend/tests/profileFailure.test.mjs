import assert from 'node:assert/strict'
import { profileFailure } from '../src/utils/profileFailure.js'

assert.equal(profileFailure({ status: 403, code: 'staging_access_denied' }).retry, false)
assert.match(profileFailure({ status: 403, code: 'staging_access_denied' }).title, /invitation/)
assert.match(profileFailure({ status: 401 }).title, /sign in/)
assert.equal(profileFailure({ status: 403 }).retry, false)
for (const error of [true, undefined, new TypeError('Failed to fetch'), { status: 503 }]) {
  assert.equal(profileFailure(error).retry, true)
}
console.log('Account access and retry messages passed.')
