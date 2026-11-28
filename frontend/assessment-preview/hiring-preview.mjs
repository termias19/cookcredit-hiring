// This view reads displayed frames. It has no reference to the recorder,
// landmark capture, applicant state, score, storage, or submission bridge.
export function currentPreviewFrame(frame, wallTime, mediaTime) {
  const age = wallTime - frame.sentAt;
  const offset = mediaTime - frame.t;
  return age >= 0 && age < 250 && offset >= -0.08 && offset < 0.25;
}

export function installBladePreview(doc = document, win = window) {
  const byId = id => doc.getElementById(id);
  const option = byId('blade-preview-option');
  const toggle = byId('blade-preview-toggle');
  const live = byId('screen-live');
  const review = byId('screen-summary');
  const rec = byId('rec-dot');
  const video = byId('video');
  const layer = byId('blade-preview-layer');
  const status = byId('blade-preview-status');
  const result = byId('blade-preview-result');
  const consent = byId('m-consent');
  const surface = doc.createElement('canvas');
  let pixels, pen, worker, ready, busy, requested, deadline, expiry, streak;
  let running = false, failed = false, chosen = false;
  let epoch = 0, previousTime = -Infinity, previousSend = -Infinity;
  let sampled = 0, segments = 0, tips = 0, junctions = 0, pendingFrame, stream;
  const now = () => win.performance.now();
  const say = value => { if (status.textContent !== value) status.textContent = value; };
  function clear() {
    win.clearTimeout(expiry);
    pen?.clearRect(0, 0, layer.width, layer.height);
  }
  function reset() {
    clear();
    streak?.interrupt();
    ++epoch;
    previousTime = previousSend = -Infinity;
    pendingFrame = undefined;
  }
  function detach() {
    reset();
    win.clearTimeout(deadline);
    if (requested !== undefined) {
      if (video.cancelVideoFrameCallback) video.cancelVideoFrameCallback(requested);
      else win.cancelAnimationFrame(requested);
    }
    requested = undefined;
    worker?.terminate();
    worker = undefined;
    stream = undefined;
    busy = ready = false;
    layer.hidden = true;
    live.classList.remove('show-blade-preview');
  }
  function unavailable() {
    detach();
    failed = true;
    say('Blade guide unavailable.');
  }
  function mark(point, color) {
    if (!Array.isArray(point) || point.length !== 2 ||
        !point.every(value => Number.isFinite(value) && value >= 0 && value <= 1)) return false;
    const x = point[0] * layer.width, y = point[1] * layer.height;
    pen.beginPath();
    pen.arc(x, y, Math.max(4, layer.width / 95), 0, 2 * Math.PI);
    pen.fillStyle = color;
    pen.fill();
    pen.strokeStyle = '#182321';
    pen.lineWidth = Math.max(1, layer.width / 340);
    pen.stroke();
    return true;
  }
  function segment(t, result, age) {
    const box = result?.box, axis = result?.axis;
    const physical = result?.rawDetected && result.stable &&
      Array.isArray(axis) && (axis.length === 3 || axis.length === 4) && axis.every(Number.isFinite) &&
      (axis.length === 3 || axis[3] > 0) &&
      Array.isArray(box) && box.length === 4 && box.every(Number.isFinite) && box[2] > 0 && box[3] > 0;
    // Both Practice paths measure this image's pixels. The native
    // measureEdgeAxis supplies center/direction and the refined line also
    // supplies a supported half-length. A rectangle alone has no axis.
    if (!streak?.observe(t, physical ? result : null, age)) return false;
    const [cx,cy,angle,halfWidth] = axis, [x,y,w,h] = box;
    const width = layer.width, height = layer.height;
    const length = Math.min(Math.hypot(w*width,h*height)*.28, (halfWidth ?? 1)*width);
    const dx = Math.cos(angle)*length, dy = Math.sin(angle)*length;
    pen.save();
    pen.beginPath(); pen.rect(x*width,y*height,w*width,h*height); pen.clip();
    pen.beginPath(); pen.moveTo(cx*width-dx,cy*height-dy); pen.lineTo(cx*width+dx,cy*height+dy);
    pen.lineWidth = Math.max(2,width/350); pen.strokeStyle = '#fff'; pen.stroke();
    pen.restore();
    return true;
  }
  function observe(data) {
    const frame = pendingFrame;
    pendingFrame = undefined;
    busy = false;
    if (!frame || data.epoch !== epoch || data.t !== frame.t || frame.sentAt !== data.sentAt ||
        doc.hidden || rec.hidden || live.hidden || video.srcObject !== stream ||
        !currentPreviewFrame(frame, now(), video.currentTime)) return;
    clear();
    ++sampled;
    const hasSegment = segment(frame.t, data.result, now()-frame.sentAt);
    if (hasSegment) ++segments;
    const measured = data.result?.landmarkStatus === 'ready' ? data.result.landmarks : null;
    const hasTip = mark(measured?.tip, '#66dcff');
    const hasJunction = mark(measured?.junction, '#ffcc68');
    if (hasTip) ++tips;
    if (hasJunction) ++junctions;
    const labels = [];
    if (hasSegment) labels.push('white segment');
    if (hasTip) labels.push('blue tip');
    if (hasJunction) labels.push('gold junction');
    say('Blade guide · ' + (labels.length ? labels.join(' · ') : 'no clear blade features'));
    if (labels.length) expiry = win.setTimeout(() => {
      clear();
      say('Blade guide · no current blade features');
    }, Math.max(0, 250 - (now() - frame.sentAt)));
  }
  function queue() {
    requested = video.requestVideoFrameCallback
      ? video.requestVideoFrameCallback((_, meta) => sample(meta.mediaTime))
      : win.requestAnimationFrame(() => sample(video.currentTime));
  }
  function sample(t) {
    requested = undefined;
    if (!worker) return;
    try {
      queue();
      if (!ready || doc.hidden || live.hidden || rec.hidden || !consent.checked || !toggle.checked ||
          video.readyState < 2 || !video.srcObject || !video.videoWidth || !video.videoHeight) return;
      if (stream !== video.srcObject) { reset(); stream = video.srcObject; }
      const clock = now();
      if (t < previousTime) reset();
      if (busy || !Number.isFinite(t) || t === previousTime || clock - previousSend < 65) return;
      // Match Practice's bounded input. Its worker resizes proposal coordinates
      // to the verifier's 448px working width internally.
      const scale = Math.min(1, 448 / Math.max(video.videoWidth, video.videoHeight));
      const width = Math.max(1, Math.round(video.videoWidth * scale));
      const height = Math.max(1, Math.round(video.videoHeight * scale));
      if (surface.width !== width || surface.height !== height) {
        reset();
        surface.width = layer.width = width;
        surface.height = layer.height = height;
      }
      pixels.drawImage(video, 0, 0, width, height);
      const rgba = pixels.getImageData(0, 0, width, height).data;
      pendingFrame = {epoch, t, sentAt: clock};
      worker.postMessage({type:'frame', ...pendingFrame, elapsed: t, pageOrigin:win.performance.timeOrigin, rgba, width, height}, [rgba.buffer]);
      busy = true;
      previousTime = t;
      previousSend = clock;
      win.clearTimeout(deadline);
      deadline = win.setTimeout(unavailable, 8000);
    } catch { unavailable(); }
  }
  function start() {
    try {
      pixels = surface.getContext('2d', {willReadFrequently:true});
      pen = layer.getContext('2d');
      if (!pixels || !pen) { unavailable(); return; }
      const current = new win.Worker(new URL('./practice-live/camera.js', import.meta.url));
      worker = current;
      streak = undefined;
      import('./practice-live/edge-streak.mjs').then(({EdgeStreak}) => {
        if (worker === current) streak = new EdgeStreak();
      }).catch(() => {});
      // Never post recording frames before this independent worker is ready.
      current.onmessage = ({data}) => {
        if (worker !== current) return;
        try {
          if (data.type === 'error') { unavailable(); return; }
          if (data.type === 'ready') {
            win.clearTimeout(deadline);
            ready = true;
            layer.hidden = false;
            live.classList.add('show-blade-preview');
            say('Blade guide · finding landmarks');
          } else if (data.type === 'result' || data.type === 'skipped') {
            win.clearTimeout(deadline);
            if (data.type === 'result') observe(data);
            else { busy = false; pendingFrame = undefined; }
          }
        } catch { unavailable(); }
      };
      current.onerror = error => { error.preventDefault(); if (worker === current) unavailable(); };
      current.onmessageerror = () => { if (worker === current) unavailable(); };
      deadline = win.setTimeout(unavailable, 45000);
      current.postMessage({type:'load'});
      status.hidden = false;
      say('Loading blade guide…');
      queue();
    } catch { unavailable(); }
  }
  function sync() {
    const hiring = doc.body.classList.contains('hiring-experience');
    option.hidden = !hiring;
    const active = hiring && !live.hidden && toggle.checked && consent.checked;
    if (active && !running) {
      running = chosen = true;
      sampled = segments = tips = junctions = 0;
      failed = false;
      result.hidden = true;
    } else if (!active && running) {
      detach();
      status.hidden = true;
      running = false;
    }
    if (active && (doc.hidden || rec.hidden)) { if (worker) detach(); }
    else if (active && !failed && !worker) start();
    if (!review.hidden && chosen) {
      const detail = sampled
        ? 'Across ' + sampled + ' sampled frames, the camera showed a blade segment in ' + segments + ', the tip in ' + tips + ', and the handle junction in ' + junctions + '.'
        : 'No fresh blade readings were available.';
      result.textContent = 'Your blade guide. ' + detail + ' Only you see these estimates. They do not affect your score.';
      result.hidden = false;
    }
    if (live.hidden && review.hidden) { chosen = false; result.hidden = true; }
  }
  const observer = new win.MutationObserver(sync);
  for (const el of [live, review, rec]) observer.observe(el, {attributes:true, attributeFilter:['hidden']});
  observer.observe(doc.body, {attributes:true, attributeFilter:['class']});
  for (const id of ['btn-reset','btn-swap-hand','btn-flip-cam']) byId(id).addEventListener('click', reset);
  byId('btn-stop').addEventListener('click', () => { if (running) { failed = true; detach(); } });
  toggle.addEventListener('change', sync);
  consent.addEventListener('change', sync);
  doc.addEventListener('visibilitychange', sync);
  win.addEventListener('pagehide', detach);
  sync();
}

if (typeof document !== 'undefined') installBladePreview();
