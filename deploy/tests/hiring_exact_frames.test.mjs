import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {gunzipSync} from 'node:zlib';
import {ExactFrameCapture, createPrivateFrameSpool} from '../hiring-exact-frames.mjs';
const config={width:320,height:2,sourceWidth:640,sourceHeight:4,modelSha256:'a'.repeat(64),runtimeSha256:'b'.repeat(64)};
const sample=(rgba,timestampMs=1000.123456789)=>({rgba,timestampMs,sessionTimeSec:.123456789,hand:'Right'});

test('captures exact pixels and fractional clocks without retaining mutable source',async()=>{
 const c=new ExactFrameCapture(config),pixels=new Uint8ClampedArray(2560).fill(7);
 assert.equal(c.record(sample(pixels)),true);pixels.fill(99);
 const result=await c.finish();assert.equal(result.complete,true);assert.equal(result.serverVerified,false);
 const bytes=Buffer.from(await result.archive.arrayBuffer());assert.equal(bytes.subarray(0,8).toString(),'CCEF0001');
 const n=bytes.readUInt32BE(8),header=JSON.parse(bytes.subarray(12,12+n));
 assert.equal(header.frames[0].timestampMs,1000.123456789);
 assert.equal(header.frames[0].sessionTimeSec,.123456789);
 assert.deepEqual(gunzipSync(bytes.subarray(12+n)),Buffer.alloc(2560,7));
 assert.equal(c.record(sample(pixels,2000)),false);
 if(process.env.EXACT_FRAME_TEST_FIXTURE)fs.writeFileSync(process.env.EXACT_FRAME_TEST_FIXTURE,bytes);
});
test('backpressure invalidates the archive instead of silently dropping inference input',async()=>{
 const c=new ExactFrameCapture(config),pixels=new Uint8Array(2560);
 assert.equal(c.record(sample(pixels,1)),true);assert.equal(c.record(sample(pixels,2)),true);
 assert.equal(c.record(sample(pixels,3)),false);
 const r=await c.finish();assert.equal(r.archive,null);assert.deepEqual(r.issues,['compression-backpressure']);
});
test('bad geometry and asset identities are rejected',()=>{
 for(const change of [{width:480},{height:3},{sourceWidth:0},{modelSha256:'x'},{runtimeSha256:null}])
  assert.throws(()=>new ExactFrameCapture({...config,...change}),/Unsupported/);
});
test('empty, invalid and nonmonotonic input cannot produce clean evidence',async()=>{
 const empty=await new ExactFrameCapture(config).finish();assert.equal(empty.archive,null);
 for(const change of [{rgba:new Uint8Array(2)},{timestampMs:NaN},{sessionTimeSec:181},{hand:'Other'}]){
  const c=new ExactFrameCapture(config);assert.equal(c.record({...sample(new Uint8Array(2560)),...change}),false);
  assert.equal((await c.finish()).archive,null);
 }
 const c=new ExactFrameCapture(config);c.record(sample(new Uint8Array(2560)));
 assert.equal(c.record(sample(new Uint8Array(2560))),false);assert.equal((await c.finish()).archive,null);
});


test('v2 retains multiple controls between frames and fresh-model context', async()=>{
 const context={initialHand:'Right',countdownSec:3,modelState:'fresh'};
 const c=new ExactFrameCapture({...config,context});context.initialHand='Left';
 const pixels=new Uint8Array(2560);
 c.record(sample(pixels,1));c.event('hand-change','Left');c.event('hand-change','Right');c.event('session-reset','Right');
 const r=await c.finish(),b=Buffer.from(await r.archive.arrayBuffer());
 const header=JSON.parse(b.subarray(12,12+b.readUInt32BE(8)));
 assert.equal(header.version,2);assert.equal(header.context.initialHand,'Right');
 assert.deepEqual(header.events.map(e=>e.beforeFrame),[1,1,1]);
 assert.equal(c.event('session-reset','Right'),false);
});
test('model continuity cannot silently claim fresh initialization',()=>{
 assert.throws(()=>new ExactFrameCapture({...config,context:{initialHand:'Right',countdownSec:3,modelState:'unknown'}}),/fresh model/);
});


test('private spooling preserves order, round trip and explicit cleanup',async()=>{
 const chunks=[],removed=[];let closed=false,openedName;
 const storage={getDirectory:async()=>({
  getFileHandle:async(name)=>{openedName=name;return {
   createWritable:async()=>({write:async bytes=>chunks.push(Buffer.from(bytes)),close:async()=>{closed=true;},abort:async()=>{closed=true;}}),
   getFile:async()=>new Blob(chunks),
  };},removeEntry:async name=>removed.push(name),
 })};
 const spool=await createPrivateFrameSpool(storage);
 await assert.rejects(()=>spool.write(1,new Uint8Array(1)),/order/);
 const c=new ExactFrameCapture({...config,spool});
 c.record(sample(new Uint8Array(2560).fill(9),1));
 const r=await c.finish();assert.equal(r.complete,true);assert.equal(c.chunks.length,0);assert.equal(closed,true);
 const bytes=Buffer.from(await r.archive.arrayBuffer()),n=bytes.readUInt32BE(8);
 assert.deepEqual(gunzipSync(bytes.subarray(12+n)),Buffer.alloc(2560,9));
 assert.deepEqual(removed,[]);await spool.dispose();await spool.dispose();
 assert.deepEqual(removed,[openedName]);assert.match(openedName,/^cookcredit-exact-[a-f0-9-]+\.tmp$/);
 await assert.rejects(()=>spool.finish(1),/Incomplete/);
});
test('spool quota/write failure invalidates archive and never falls back to unbounded memory',async()=>{
 const c=new ExactFrameCapture({...config,spool:{write:async()=>{throw Error('quota');},finish:async()=>{throw Error('must not finalize');}}});
 c.record(sample(new Uint8Array(2560)));
 const r=await c.finish();assert.equal(r.complete,false);assert.equal(r.archive,null);assert.equal(c.chunks.length,0);
 assert.deepEqual(r.issues,['compression-failed']);
});
