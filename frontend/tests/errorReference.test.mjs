import test from 'node:test'
import assert from 'node:assert/strict'
import { errorReference } from '../src/utils/errorReference.js'
test('server reference is exposed only for server errors and valid IDs', () => {
  const id = 'a'.repeat(32)
  assert.equal(errorReference({requestId:id}, {status:500}), id)
  assert.equal(errorReference({}, {status:503, headers:{get:()=>id}}), id)
  assert.equal(errorReference({requestId:'<script>untrusted</script>'}, {status:500}), null)
  assert.equal(errorReference({requestId:id}, {status:401}), null)
})
