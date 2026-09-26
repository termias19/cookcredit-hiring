// Client capture claims only. These never authorize a score or a hiring decision.
export class HiringCapture {
  constructor({video, hand, countdownSec, detectorWidth, now, exactFrames = null}) {
    this.start = now;
    this.done = false;
    this.exactFrames = exactFrames;
    this.claim = {version: 2, profile: 'knife-motion-v1', recording: 'camera-stream',
      mirrored: false, sourceWidth: video.videoWidth, sourceHeight: video.videoHeight,
      initialHand: hand, countdownSec, detectorWidth, timing: 'performance-clock-approximate',
      modelAsset: 'hand_landmarker.task', modelHashVerified: false,
      events: [], samples: [], durationMs: 0, issues: []};
  }
  issue(reason) {
    if (!this.claim.issues.includes(reason)) this.claim.issues.push(reason);
  }
  event(type, now, hand) {
    if (this.done) return;
    if (this.claim.events.length >= 128) { this.issue('event-limit'); return; }
    this.claim.events.push({type, offsetMs: Math.round(now-this.start), hand});
    this.exactFrames?.event(type, hand);
  }
  // The overlay must supply pixels immediately before the corresponding model call.
  beforeInference({rgba, timestampMs, now, startedAt, hand}) {
    if (this.done || !this.exactFrames) return false;
    return this.exactFrames.record({rgba, timestampMs, sessionTimeSec: (now-startedAt)/1000, hand});
  }
  inferenceFailed() { this.exactFrames?.issue('inference-failed'); }
  async exactEvidence() {
    if (!this.done) throw new Error('The hiring recording has not finished.');
    if (!this.exactFrames) return null;
    if (this.claim.issues.length) this.exactFrames.issue('recording-capture-issue');
    return this.exactFrames.finish();
  }
  sample({now, startedAt, hand, video}) {
    if (this.done) return;
    if (video.videoWidth !== this.claim.sourceWidth || video.videoHeight !== this.claim.sourceHeight)
      this.issue('geometry-changed');
    if (this.claim.samples.length >= 6000) { this.issue('sample-limit'); return; }
    this.claim.samples.push([Math.round(now-this.start), Math.round(now-startedAt), hand]);
  }
  finish(now, hasVideo) {
    if (this.done) return;
    this.done = true;
    this.claim.durationMs = Math.round(now-this.start);
    if (!hasVideo) this.issue('recording-unavailable');
  }
  snapshot() {
    if (!this.done) throw new Error('The hiring recording has not finished.');
    return JSON.parse(JSON.stringify(this.claim));
  }
}
