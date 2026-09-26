// Lossless inference-input evidence. Client claims never authorize a result.
// Not enabled by the live overlay until storage, replay and device tests pass.
const MAX_BYTES = 80 * 1024 * 1024;
const MAX_FRAMES = 6000;
const MAX_PENDING = 2;
const MAGIC = new TextEncoder().encode('CCEF0001');

export class ExactFrameCapture {
  constructor({width, height, sourceWidth, sourceHeight, modelSha256, runtimeSha256, context = null, spool = null}) {
    if (width !== 320 || !Number.isInteger(height) || height < 1 || height > 1280 ||
        ![sourceWidth, sourceHeight].every(n => Number.isInteger(n) && n > 0 && n <= 8192) ||
        height !== Math.max(1, Math.round(width * sourceHeight / sourceWidth)) ||
        ![modelSha256, runtimeSha256].every(s => typeof s === 'string' && /^[a-f0-9]{64}$/.test(s))) {
      throw new Error('Unsupported exact-frame geometry or asset identity');
    }
    if (context !== null && (Object.keys(context).sort().join(',') !== 'countdownSec,initialHand,modelState' ||
        !['Left', 'Right'].includes(context.initialHand) || context.modelState !== 'fresh' ||
        !Number.isInteger(context.countdownSec) || context.countdownSec < 0 || context.countdownSec > 30)) {
      throw new Error('Exact replay requires an explicit fresh model and session context');
    }
    this.spool = spool;
    this.writeTail = Promise.resolve();
    this.context = context === null ? null : {...context};
    this.events = [];
    this.config = {width, height, sourceWidth, sourceHeight, modelSha256, runtimeSha256};
    this.rows = [];
    this.chunks = [];
    this.pending = new Set();
    this.issues = [];
    this.bytes = 0;
    this.closed = false;
    this.lastTimestamp = -1;
  }

  issue(reason) { if (!this.issues.includes(reason)) this.issues.push(reason); }

  // Call immediately before inference with its actual RGBA input and clocks.
  // Copies pixels synchronously; compression runs asynchronously and can fail.
  record({rgba, timestampMs, sessionTimeSec, hand}) {
    if (this.closed || this.issues.length) return false;
    if (!(rgba instanceof Uint8ClampedArray || rgba instanceof Uint8Array) ||
        rgba.byteLength !== this.config.width * this.config.height * 4 ||
        !Number.isFinite(timestampMs) || timestampMs < 0 || timestampMs <= this.lastTimestamp ||
        !Number.isFinite(sessionTimeSec) || sessionTimeSec < 0 || sessionTimeSec > 180 ||
        !['Left', 'Right'].includes(hand)) {
      this.issue('invalid-input'); return false;
    }
    if (this.rows.length >= MAX_FRAMES) { this.issue('frame-limit'); return false; }
    if ((this.rows.length + 1) * rgba.byteLength > 512 * 1024 * 1024) {
      this.issue('expanded-byte-limit'); return false;
    }
    if (this.rows.length && timestampMs - this.rows[0].timestampMs > 180000) {
      this.issue('duration-limit'); return false;
    }
    if (this.pending.size >= MAX_PENDING) { this.issue('compression-backpressure'); return false; }
    this.lastTimestamp = timestampMs;
    const index = this.rows.length;
    const pixels = new Uint8Array(rgba); // detach from the canvas/model's mutable input
    this.rows.push({timestampMs, sessionTimeSec, hand});
    const previousWrite = this.writeTail;
    const task = (async () => {
      try {
        const hash = await crypto.subtle.digest('SHA-256', pixels);
        const stream = new Blob([pixels]).stream().pipeThrough(new CompressionStream('gzip'));
        const compressed = new Uint8Array(await new Response(stream).arrayBuffer());
        if (this.bytes + compressed.byteLength > MAX_BYTES) { this.issue('byte-limit'); return; }
        this.bytes += compressed.byteLength;
        await previousWrite;
        if (this.issues.length) return;
        if (this.spool) await this.spool.write(index, compressed);
        else this.chunks[index] = compressed;
        Object.assign(this.rows[index], {
          sha256: Array.from(new Uint8Array(hash), x => x.toString(16).padStart(2, '0')).join(''),
          compressedBytes: compressed.byteLength,
        });
      } catch { this.issue('compression-failed'); }
    })();
    this.writeTail = task;
    this.pending.add(task);
    task.finally(() => this.pending.delete(task));
    return true;
  }

  event(type, hand) {
    if (this.closed || this.issues.length) return false;
    if (!this.context || !['hand-change', 'session-reset'].includes(type) || !['Left', 'Right'].includes(hand)) {
      this.issue('invalid-control'); return false;
    }
    if (this.events.length >= 128) { this.issue('event-limit'); return false; }
    this.events.push({type, hand, beforeFrame: this.rows.length});
    return true;
  }

  async finish() {
    this.closed = true;
    await Promise.all(this.pending);
    if (!this.rows.length) this.issue('no-frames');
    if (this.issues.length) return {complete: false, issues: [...this.issues], serverVerified: false, archive: null};
    const header = new TextEncoder().encode(JSON.stringify({
      version: this.context ? 2 : 1, encoding: 'rgba8-gzip-per-frame', trust: 'client-claim',
      ...(this.context ? {context: this.context, events: this.events} : {}),
      ...this.config, frames: this.rows,
    }));
    if (header.byteLength > 1024 * 1024) {
      this.issue('header-limit');
      return {complete: false, issues: [...this.issues], serverVerified: false, archive: null};
    }
    let payload = this.chunks;
    if (this.spool) {
      try {
        const file = await this.spool.finish(this.rows.length);
        if (!(file instanceof Blob) || file.size !== this.bytes) throw new Error('Incomplete spool');
        payload = [file];
      } catch {
        this.issue('spool-failed');
        return {complete: false, issues: [...this.issues], serverVerified: false, archive: null};
      }
    }
    const length = new Uint8Array(4);
    new DataView(length.buffer).setUint32(0, header.byteLength, false);
    return {complete: true, issues: [], serverVerified: false,
      archive: new Blob([MAGIC, length, header, ...payload], {type: 'application/octet-stream'})};
  }
}


// Uses a unique origin-private temporary file; never a user-selected directory.
// The caller must dispose AFTER upload completes or after abandoning capture.
export async function createPrivateFrameSpool(storage = navigator.storage) {
  if (!storage?.getDirectory) throw new Error('Private frame storage is unavailable');
  const root = await storage.getDirectory();
  const name = 'cookcredit-exact-' + crypto.randomUUID() + '.tmp';
  const handle = await root.getFileHandle(name, {create: true});
  let writer;
  try { writer = await handle.createWritable(); }
  catch (error) { await root.removeEntry(name); throw error; }
  let count = 0, finalizing = null, disposed = false;
  return {
    async write(index, bytes) {
      if (disposed || finalizing || index !== count || !(bytes instanceof Uint8Array)) throw new Error('Invalid spool write order');
      await writer.write(bytes); count++;
    },
    async finish(expected) {
      if (disposed || expected !== count) throw new Error('Incomplete frame spool');
      if (!finalizing) finalizing = (async () => { await writer.close(); return handle.getFile(); })();
      return finalizing;
    },
    async dispose() {
      if (disposed) return;
      disposed = true;
      try { if (finalizing) await finalizing; else await writer.abort(); }
      finally { await root.removeEntry(name); }
    },
  };
}
