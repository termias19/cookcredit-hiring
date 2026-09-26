import test from 'node:test'
import assert from 'node:assert/strict'
import {validateOriginalLandmarks, landmarkFrameAt} from '../src/utils/originalLandmarks.js'
const hand = Array.from({length:21}, () => [0.25,0.75])
const data = {version:1,timebase:'recording-ms',mirrored:false,frames:[[0,hand,null],[100,null,null],[400,hand,hand]]}
test('seeking both directions uses original samples and clears tracking gaps',()=>{
 const frames=validateOriginalLandmarks(data)
 assert.equal(landmarkFrameAt(frames,.4),frames[2])
 assert.equal(landmarkFrameAt(frames,.05),frames[0])
 assert.deepEqual(landmarkFrameAt(frames,.15),[100,null,null])
 assert.equal(landmarkFrameAt(frames,.35),null)
 assert.equal(landmarkFrameAt(frames,-1),null)
 assert.equal(landmarkFrameAt(frames,4),null)
})
test('corrupt timestamps, oversized sequences and invalid points fail closed',()=>{
 for(const frames of [[[100,hand,null],[50,hand,null]],[[0,[[NaN,0]],null]],Array(1901).fill([0,null,null]),[[120001,null,null]]])
  assert.throws(()=>validateOriginalLandmarks({...data,frames}))
 assert.throws(()=>validateOriginalLandmarks({...data,mirrored:true}))
})


const visual={width:1280,height:720,bladeExtendK:3.2,knifePresent:true,knifeConf:.91,knifeWorker:true,bladeTrail:[[100,200],[103,201]]}
test('original engine visual state survives seeking, invalid renderer and knife state fail closed',()=>{
 const full={...data,version:2,renderer:'a'.repeat(64),frames:data.frames.map(row=>[...row,structuredClone(visual)])}
 assert.equal(validateOriginalLandmarks(full),full.frames)
 assert.deepEqual(landmarkFrameAt(full.frames,.4)[3],visual)
 for(const change of [{width:0},{knifeConf:NaN},{knifePresent:1},{bladeExtendK:99},{bladeTrail:Array(49).fill([0,0])}]) {
  const bad=structuredClone(full); Object.assign(bad.frames[0][3],change)
  assert.throws(()=>validateOriginalLandmarks(bad))
 }
 assert.throws(()=>validateOriginalLandmarks({...full,renderer:'https://evil.invalid/script.js'}))
})
