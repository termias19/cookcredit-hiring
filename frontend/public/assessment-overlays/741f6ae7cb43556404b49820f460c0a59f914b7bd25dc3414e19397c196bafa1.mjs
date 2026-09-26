// Generated from the pinned CookCredit Engine renderer; no inference.
const HAND_CONNECTIONS = [
  [0,1],[1,2],[2,3],[3,4],
  [0,5],[5,6],[6,7],[7,8],
  [5,9],[9,10],[10,11],[11,12],
  [9,13],[13,14],[14,15],[15,16],
  [13,17],[17,18],[18,19],[19,20],
  [0,17],
];
const WRIST=0, INDEX_MCP=5;
export function drawOriginalEngineOverlay(ctx,row) {
const visual=row[3];
const state={...visual,ctx,canvas:{width:visual.width,height:visual.height},mode:'test',bladeTrail:visual.bladeTrail.map(([x,y])=>({x,y}))};
const hand=points=>points?.map(([x,y])=>({x,y}));
drawOverlay(hand(row[1]),hand(row[2]));
function drawOverlay(knifeLm, otherLm) {
  const ctx = state.ctx;
  const W = state.canvas.width, H = state.canvas.height;
  ctx.clearRect(0, 0, W, H);
  const play = state.mode === 'play';

  // TEST (assessment) shows the raw skeleton; PLAY hides it under a glove.
  if (!play) {
    if (otherLm) drawHand(otherLm, W, H, 'rgba(180,0,180,0.5)', 'rgba(180,0,180,0.7)', 2);
    if (knifeLm) drawHand(knifeLm, W, H, 'rgba(0,220,0,0.9)', 'rgba(0,255,0,0.95)', 3);
  }

  // Blade-tip "flow" trace (both modes) -- the KNIFE is the tracer.
  drawBladeFlow();

  if (knifeLm) {
    const wx = knifeLm[WRIST].x * W,     wy = knifeLm[WRIST].y * H;
    const ix = knifeLm[INDEX_MCP].x * W, iy = knifeLm[INDEX_MCP].y * H;

    if (play) drawGlove(knifeLm, W, H);        // animated glove hides the landmarks

    // Predicted blade-locator line (wrist -> index-knuckle axis -> tip).
    drawBlade(wx, wy, ix, iy);

    if (!play) {
      ctx.beginPath();
      ctx.arc(wx, wy, 10, 0, Math.PI * 2);
      ctx.strokeStyle = 'rgba(255,80,80,0.9)';
      ctx.lineWidth = 3; ctx.stroke();
      if (state.knifeWorker) drawKnifeBadge(wx, wy, ix, iy);
    }
  }

  // Game juice/combo/score pops on top (PLAY only). Text is un-mirrored since
  // the overlay canvas is CSS-flipped (selfie view).
  if (play && state.game) state.game.drawFx(ctx, unmirrorText);
}
function drawBlade(wx, wy, ax, ay) {
  const ctx = state.ctx;
  const dx = ax - wx, dy = ay - wy;
  const len = Math.hypot(dx, dy) || 1;
  const K = state.bladeExtendK;
  const tipX = wx + K * dx,     tipY = wy + K * dy;       // predicted blade tip
  const baseX = wx + 1.05 * dx, baseY = wy + 1.05 * dy;   // blade exits the fist
  const present = state.knifePresent;
  const rgb = present ? '43,217,184' : '240,244,250';     // teal confirmed / white predicted
  const w = Math.max(2.5, 0.09 * len);                    // slim line, scales with hand

  ctx.lineCap = 'round';
  // Soft halo (wider, faint) -> reads as a glow without per-frame shadowBlur.
  ctx.beginPath(); ctx.moveTo(baseX, baseY); ctx.lineTo(tipX, tipY);
  ctx.strokeStyle = 'rgba(' + rgb + ',0.16)'; ctx.lineWidth = w * 2.6; ctx.stroke();
  // Crisp core line.
  ctx.beginPath(); ctx.moveTo(baseX, baseY); ctx.lineTo(tipX, tipY);
  ctx.strokeStyle = 'rgba(' + rgb + ',0.95)'; ctx.lineWidth = w; ctx.stroke();
  // Tip reticle = the locator point + a faint outer ring.
  ctx.beginPath(); ctx.arc(tipX, tipY, w * 0.85, 0, Math.PI * 2);
  ctx.fillStyle = 'rgba(' + rgb + ',0.98)'; ctx.fill();
  ctx.beginPath(); ctx.arc(tipX, tipY, w * 1.9, 0, Math.PI * 2);
  ctx.strokeStyle = 'rgba(' + rgb + ',0.40)'; ctx.lineWidth = 1.5; ctx.stroke();
}
function drawBladeFlow() {
  const t = state.bladeTrail;
  if (t.length < 2) return;
  const ctx = state.ctx;
  const accent = '130,180,255';   // light-blue motion trail (the "flow")
  ctx.lineCap = 'round';
  for (let i = 1; i < t.length; ++i) {
    const a = i / t.length;                       // newer segments brighter/thicker
    ctx.beginPath();
    ctx.moveTo(t[i - 1].x, t[i - 1].y);
    ctx.lineTo(t[i].x, t[i].y);
    ctx.strokeStyle = 'rgba(' + accent + ',' + (0.08 + 0.5 * a).toFixed(3) + ')';
    ctx.lineWidth = 1 + 5 * a;
    ctx.stroke();
  }
}
function drawKnifeBadge(wx, wy, mx, my) {
  const ctx = state.ctx;
  const K = state.bladeExtendK + 0.25;
  const tx = wx + K * (mx - wx), ty = wy + K * (my - wy);
  const present = state.knifePresent;
  const accent = present ? 'rgba(0,230,140,0.95)' : 'rgba(255,180,60,0.9)';
  const label = present ? 'knife ' + Math.round(state.knifeConf * 100) + '%' : 'scanning…';
  ctx.font = '600 14px system-ui, -apple-system, sans-serif';
  const tw = ctx.measureText(label).width;
  const padX = 8, h = 22, x = tx + 10, y = ty - h / 2;
  ctx.beginPath();
  if (ctx.roundRect) ctx.roundRect(x, y, tw + padX * 2, h, 6);
  else ctx.rect(x, y, tw + padX * 2, h);
  ctx.fillStyle = 'rgba(15,18,24,0.66)'; ctx.fill();
  // geometric status mark (filled diamond), not an emoji
  ctx.beginPath();
  const dcx = x + padX * 0.6, dcy = y + h / 2, r = 4;
  ctx.moveTo(dcx, dcy - r); ctx.lineTo(dcx + r, dcy); ctx.lineTo(dcx, dcy + r); ctx.lineTo(dcx - r, dcy);
  ctx.closePath(); ctx.fillStyle = accent; ctx.fill();
  ctx.fillStyle = accent;
  ctx.fillText(label, x + padX + 6, y + h / 2 + 5);
}
function drawHand(lm, W, H, edgeColor, jointColor, lineWidth) {
  const ctx = state.ctx;
  ctx.strokeStyle = edgeColor;
  ctx.lineWidth = lineWidth;
  ctx.beginPath();
  for (const [a, b] of HAND_CONNECTIONS) {
    ctx.moveTo(lm[a].x * W, lm[a].y * H);
    ctx.lineTo(lm[b].x * W, lm[b].y * H);
  }
  ctx.stroke();
  ctx.fillStyle = jointColor;
  for (const p of lm) {
    ctx.beginPath();
    ctx.arc(p.x * W, p.y * H, 3, 0, Math.PI * 2);
    ctx.fill();
  }
}
}
