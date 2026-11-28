import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { currentPreviewFrame } from '../assessment-preview/hiring-preview.mjs';
import { bundleForAssetMap, hiringPreviewHtml, pinnedHtml } from '../scripts/assessment-preview-package.mjs';

test('blade markers expire using both the displayed camera time and the elapsed clock', () => {
  const frame = { t: 6, sentAt: 4711 };
  assert.equal(currentPreviewFrame(frame, 4791, 6.08), true);
  assert.equal(currentPreviewFrame(frame, 4961, 6.01), false);
  assert.equal(currentPreviewFrame(frame, 4791, 6.25), false);
  assert.equal(currentPreviewFrame(frame, 4791, 0), false);
  assert.equal(currentPreviewFrame(frame, 4710, 6), false);
  assert.equal(currentPreviewFrame(frame, 4791, NaN), false);
});

test('the independent applicant preview uses the pinned Hiring source and exact shared asset digests', async () => {
  assert.throws(() => hiringPreviewHtml(Buffer.from('<!doctype html>')), /changed Hiring assessment/);
  const manifest = JSON.parse(await readFile(new URL('../scripts/hiring-assessment-release.json', import.meta.url)));
  assert.equal(manifest.files['/hiring/index.html'].sha256, pinnedHtml);
  const shared = JSON.parse(await readFile(new URL('../assessment-preview/practice-assets.json', import.meta.url)));
  assert.match(bundleForAssetMap(shared), /^[a-f0-9]{64}$/);
  assert.equal(bundleForAssetMap(shared), bundleForAssetMap(Object.fromEntries(Object.entries(shared).reverse())));
  assert.notEqual(bundleForAssetMap(shared), bundleForAssetMap({...shared,'practice-live/camera.js':'0'.repeat(64)}));
  for (const name of ['practice-live/camera.js','practice-live/edge-streak.mjs','practice-live/landmarks/grip-forest.bin',
    'practice-live/landmarks/shape-patterns.bin','practice-live/landmarks/proposal-native.wasm']) {
    assert.match(shared[name], /^[a-f0-9]{64}$/);
  }
  if ('practice-live/landmarks/steel-proposal.mjs' in shared) {
    assert.match(shared['practice-live/landmarks/steel-head.bin'], /^[a-f0-9]{64}$/);
  }
});
