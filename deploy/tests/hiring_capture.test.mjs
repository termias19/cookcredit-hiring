import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {HiringCapture} from '../hiring-capture.mjs';
const video = {videoWidth:1920, videoHeight:1080};
function capture() { return new HiringCapture({video, hand:'Right', countdownSec:3, detectorWidth:480, now:100}); }

test('timing, hand changes, geometry changes and snapshots stay explicit claims', () => {
  const c = capture();
  c.sample({now:110, startedAt:99, hand:'Right', video});
  c.sample({now:150, startedAt:140, hand:'Left', video:{videoWidth:1280, videoHeight:720}});
  assert.throws(() => c.snapshot(), /not finished/);
  c.finish(200, true);
  const result = c.snapshot();
  assert.deepEqual(result.samples, [[10,11,'Right'],[50,10,'Left']]);
  assert.deepEqual(result.issues, ['geometry-changed']);
  assert.equal(result.modelHashVerified, false);
  result.samples.length = 0;
  assert.equal(c.snapshot().samples.length, 2);
  c.finish(300, false);
  assert.equal(c.snapshot().durationMs, 100);
});

test('missing video and excessive sampling are never silently clean', () => {
  const c = capture();
  for(let i=0;i<6002;i++) c.sample({now:100+i, startedAt:100, hand:'Right', video});
  c.finish(6200, false);
  assert.equal(c.snapshot().samples.length, 6000);
  assert.deepEqual(c.snapshot().issues, ['sample-limit','recording-unavailable']);
});

if (process.argv[2]) {
  const app = fs.readFileSync(process.argv[2], 'utf8');
  const setup = app.slice(app.indexOf('function setupRecorder()'), app.indexOf('function updateCoachUI('));
  for (const hiring of [false, true]) test(`actual transformed recorder uses ${hiring ? 'camera' : 'learning composite'} stream`, () => {
    const camera = {}, composite = {};
    const state = {hiring, video, stream:camera, knifeHand:'Right', countdownSec:3, detW:480};
    class Recorder {
      constructor(stream) { this.stream = stream; }
      addEventListener() {}
      start() { this.started = true; }
    }
    let surfaces = 0;
    const context = {state, HiringCapture, MediaRecorder:Recorder, window:{MediaRecorder:Recorder},
      preferredRecordingMimeType:()=>'', stopCompositeRecordingSurface:()=>{},
      createCompositeRecordingSurface:()=>{surfaces++;return {stream:composite};},
      performance:{now:()=>100}, renderCompositeRecordingFrame:()=>{}, console};
    vm.runInNewContext(setup+';setupRecorder();', context);
    assert.equal(state.recorder.stream, hiring ? camera : composite);
    assert.equal(surfaces, hiring ? 0 : 1);
    assert.equal(state.recordingIncludesAnalysis, !hiring);
    assert.equal(!!state.hiringCapture, hiring);
  });
}


test('control events retain repeated hand changes between inference frames', () => {
  const c = capture();
  c.event('hand-change', 110, 'Left');
  c.event('hand-change', 111, 'Right');
  c.event('session-reset', 115, 'Right');
  c.finish(200, true);
  c.event('session-reset', 205, 'Right');
  assert.equal(c.snapshot().version, 2);
  assert.deepEqual(c.snapshot().events, [
    {type:'hand-change',offsetMs:10,hand:'Left'},
    {type:'hand-change',offsetMs:11,hand:'Right'},
    {type:'session-reset',offsetMs:15,hand:'Right'},
  ]);
});

test('control-event overflow is explicit and bounded', () => {
  const c = capture();
  for(let i=0;i<130;i++) c.event('session-reset',100+i,'Right');
  c.finish(300,true);
  assert.equal(c.snapshot().events.length,128);
  assert.deepEqual(c.snapshot().issues,['event-limit']);
});


test('optional exact capture receives unrounded clocks and model failures without changing legacy metadata',async()=>{
 const calls=[];const exactFrames={record:x=>{calls.push(x);return true;},event:(...x)=>calls.push(x),issue:x=>calls.push(x),finish:async()=>({complete:false})};
 const c=new HiringCapture({video,hand:'Right',countdownSec:3,detectorWidth:320,now:100,exactFrames});
 const pixels=new Uint8Array(4);
 assert.equal(c.beforeInference({rgba:pixels,timestampMs:101,now:100.123456789,startedAt:99.987654321,hand:'Right'}),true);
 assert.equal(calls[0].sessionTimeSec,(100.123456789-99.987654321)/1000);
 c.event('hand-change',101,'Left');c.inferenceFailed();
 await assert.rejects(()=>c.exactEvidence(),/not finished/);
 c.finish(200,true);assert.deepEqual(await c.exactEvidence(),{complete:false});
 assert.equal(c.snapshot().version,2);assert.equal('exactFrames' in c.snapshot(),false);
 assert.equal(calls.includes('inference-failed'),true);
 assert.equal(c.beforeInference({}),false);
});
