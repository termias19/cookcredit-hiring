import test from 'node:test'
import assert from 'node:assert/strict'
import { containedFrame, HAND_EDGES } from '../src/utils/landmarkGeometry.js'

test('landscape recording keeps hands aligned inside a portrait reel without cropping', () => {
  assert.deepEqual(containedFrame(360, 640, 1280, 720), {x:0,y:218.75,width:360,height:202.5})
})
test('portrait recording maps exactly and landscape report has horizontal bars', () => {
  assert.deepEqual(containedFrame(360,640,720,1280), {x:0,y:0,width:360,height:640})
  assert.deepEqual(containedFrame(640,360,720,1280), {x:218.75,y:0,width:202.5,height:360})
})
test('unloaded or invalid dimensions cannot draw misaligned landmarks', () => {
  for (const n of [0, -1, NaN, Infinity]) assert.equal(containedFrame(360,640,n,720), null)
  assert.ok(HAND_EDGES.every(edge => edge.length === 2 && edge.every(n => Number.isInteger(n) && n >= 0 && n < 21)))
})
