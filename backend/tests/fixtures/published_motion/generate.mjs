// Run from any directory: node generate.mjs <directory containing baseline-wrist.js and baseline-score.js>
// Inputs are synthetic signals, not real applicants or proof of video accuracy.
import { readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { join } from 'node:path';

const expectedHashes = {
  'wrist.js': '046790be9c6a2879659c956994d997f09c02502fe474de3c29ed631871135c1e',
  'score.js': '1be9ba8eea8360cbdda813b4bc49bb949ae2194fb7e8d37aeb51168222c60a1d',
};
async function published(name) {
  const bytes = await readFile(join(process.argv[2], `baseline-${name}`));
  if (createHash('sha256').update(bytes).digest('hex') !== expectedHashes[name]) {
    throw new Error(`Published source hash changed: ${name}`);
  }
  return import(`data:text/javascript;base64,${bytes.toString('base64')}`);
}
const { WristStrokeDetector, WristMotionStats } = await published('wrist.js');
const { scoreSession } = await published('score.js');
const signal = (count, fn) => Array.from({length: count}, (_, i) => fn(i, i / 10));
const cases = [
  ['empty', []],
  ['stationary', signal(200, (i, t) => [t, 320, 300])],
  ['frozen_jitter', signal(200, (i, t) => [t, 320 + Math.cos(i), 300 + Math.sin(i)])],
  ['early_subthreshold_peak', [0, 0, 24, 0, 0].map((y, i) => [i / 10, 320, y])],
  ['steady_vertical', signal(600, (i, t) => [t, 320 + 2 * Math.cos(i), 300 + 60 * Math.sin(i * 0.9)])],
  ['horizontal_motion', signal(600, (i, t) => [t, 320 + 100 * Math.cos(i * .9), 300 + 30 * Math.sin(i * .9)])],
  ['variable_depth_and_tempo', signal(600, (i, t) => [t, 320 + 9 * Math.sin(i * .2), 300 + (35 + 25 * Math.sin(i * .07)) * Math.sin(i * .8 + 2 * Math.sin(i * .08))])],
  ['pause_then_restart', signal(600, (i, t) => [t, 320, 300 + (i > 200 && i < 400 ? 0 : 70 * Math.sin(i * .75))])],
  ['irregular_sampling', signal(350, (i, t) => [t + .018 * Math.sin(i * .31), 320 + 3 * Math.sin(i), 300 + 55 * Math.sin(i * .71)])],
  ['short_capture', signal(29, (i, t) => [t, 320, 300 + 60 * Math.sin(i * .9)])],
];
const fixtures = cases.map(([name, samples]) => {
  const detector = new WristStrokeDetector(), stats = new WristMotionStats();
  const strokeTimes = [], strokeAmps = [];
  samples.forEach(([t, x, y], i) => {
    stats.update(x, y);
    const event = detector.update(y, i, t);
    if (event) { strokeTimes.push(event.peakTSec); strokeAmps.push(event.amplitudePx); }
  });
  const score = scoreSession({strokeTimes, strokeAmps, pctChop: stats.pctChop()});
  const expected = Object.fromEntries(['overall', 'rhythm', 'consistency', 'form', 'strokes', 'cadence'].map(k => [k, score[k]]));
  return {name, samples, expected: {...expected, motionPercent: stats.pctMotion(), strokeTimes, strokeAmplitudes: strokeAmps}};
});
await writeFile(new URL('golden.json', import.meta.url), JSON.stringify({
  source: 'https://cookcredit-knife-demo.web.app/', sourceHashes: expectedHashes,
  scope: 'Numerical parity only; synthetic inputs do not validate video extraction or hiring decisions.', fixtures,
}, null, 2) + '\n');
console.log(`Generated ${fixtures.length} cases from hash-verified published JavaScript.`);
