import test from 'node:test'
import assert from 'node:assert/strict'
import { payRangeError } from '../src/utils/payRangeError.js'
test('valid hourly ranges include equal endpoints and zero', () => {
  for (const pair of [['20', '25'], ['20', '20'], ['0', '20'], ['9999', '10000']]) assert.equal(payRangeError(...pair), '')
})
test('invalid ranges cannot be silently rounded or reversed', () => {
  assert.match(payRangeError('30', '20'), /minimum cannot exceed/)
  for (const pair of [['-1', '20'], ['20.5', '25'], ['20', '10001'], ['NaN', '30'], ['20', 'Infinity']]) assert.match(payRangeError(...pair), /whole hourly amounts/)
})
