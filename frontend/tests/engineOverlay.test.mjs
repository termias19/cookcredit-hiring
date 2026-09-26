import test from 'node:test'
import assert from 'node:assert/strict'
import {readFile} from 'node:fs/promises'
import {createHash} from 'node:crypto'
import {captureFullOverlay} from '../scripts/engine-overlay-adapter.mjs'
const golden=JSON.parse(await readFile(new URL('./fixtures/engine-overlay/golden.json',import.meta.url),'utf8'))
const {drawOriginalEngineOverlay}=await import(`../public/assessment-overlays/${golden.renderer}.mjs`)

test('replay matches original published engine canvas commands for hands, predicted knife, confidence and trail',()=>{
 for(const {row,traceSha256,operations} of golden.fixtures){
  const ops=[]
  const ctx=new Proxy({},{get:(_,key)=>(...args)=>{ops.push([key,...args]);if(key==='measureText')return{width:64}},set:(_,key,value)=>{ops.push([key,value]);return true}})
  drawOriginalEngineOverlay(ctx,row)
  assert.equal(ops.length,operations)
  assert.equal(createHash('sha256').update(JSON.stringify(ops)).digest('hex'),traceSha256)
 }
})
test('capture adapter preserves original sample clock and tracking gaps within upload limits',async()=>{
 const original=await readFile(new URL('./fixtures/engine-overlay/original-capture.mjs',import.meta.url),'utf8')
 const adapted=captureFullOverlay('hiringLandmarks.add(originalLandmarkTime, knifeLm, otherLm)',original,golden.renderer)
 const {createLandmarkCapture}=await import('data:text/javascript;base64,'+Buffer.from(adapted.capture).toString('base64'))
 const capture=createLandmarkCapture(), visual=golden.fixtures[0].row[3], hand=golden.fixtures[0].row[1].map(([x,y])=>({x,y}))
 capture.start(10);capture.add(10,hand,null,visual);capture.add(10.01,hand,null,visual);capture.add(10.1,null,null,visual)
 const result=capture.finish()
 assert.equal(result.version,2);assert.equal(result.renderer,golden.renderer)
 assert.deepEqual(result.frames.map(r=>r[0]),[0,100]);assert.equal(result.frames[1][1],null)
 assert.deepEqual(result.frames[0][3],visual)
 capture.start(0)
 const maxVisual={...visual,width:8192,height:8192,bladeTrail:Array(48).fill([-163840.99,163840.99])}
 const maxHand=Array(21).fill({x:-.9999,y:1.9999})
 for(let t=0;t<=120000;t+=66) capture.add(t/1000,maxHand,maxHand,maxVisual)
 assert.ok(Buffer.byteLength(JSON.stringify(capture.finish()))<4*1024*1024)
 capture.add(121,maxHand,null,visual);assert.equal(capture.finish(),null)
 assert.throws(()=>captureFullOverlay('changed engine',original,golden.renderer))
})
