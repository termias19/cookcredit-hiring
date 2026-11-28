import { createHash } from 'node:crypto';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

export const pinnedHtml = 'f2a01b5677db11bcded36cad2e5e96c4bb466379f5e6f4b0c970b6237bb1b240';
const digest = data => createHash('sha256').update(data).digest('hex');
export function bundleForAssetMap(manifest) {
  const ordered = Object.entries(manifest).sort(([a],[b]) => a < b ? -1 : a > b ? 1 : 0);
  return digest(Buffer.from(ordered.map(([path,hash]) => path + ' ' + hash + '\n').join('')));
}
function after(source, anchor, addition) {
  if (source.split(anchor).length !== 2) throw new Error('Hiring preview cannot find its pinned HTML anchor');
  return source.replace(anchor, anchor + addition);
}

export function hiringPreviewHtml(bytes) {
  if (digest(bytes) !== pinnedHtml) throw new Error('Review the changed Hiring assessment before building the blade preview');
  let html = bytes.toString('utf8');
  html = after(html, '<link rel="stylesheet" href="style.css">', '\n  <link rel="stylesheet" href="hiring-preview.css">');
  const consentLabel = '      <label class="consent biometric">';
  if (html.split(consentLabel).length !== 2) throw new Error('Hiring preview consent anchor changed');
  html = html.replace(consentLabel, `      <label id="blade-preview-option" class="consent" hidden>
        <input id="blade-preview-toggle" type="checkbox">
        <span><b>Show blade guides (optional).</b> A white line marks a visible blade segment. Blue marks the tip and gold marks where the blade meets the handle. These estimates stay on this device and do not affect your score.</span>
      </label>
` + consentLabel);
  html = after(html, '<canvas id="overlay"></canvas>', '\n      <canvas id="blade-preview-layer" hidden aria-hidden="true"></canvas>');
  html = after(html, '<div id="coach-banner" class="coach-banner" hidden></div>', '\n      <span id="blade-preview-status" hidden></span>');
  html = after(html, '<video id="result-video" controls playsinline preload="metadata"></video>', '\n          <p id="blade-preview-result" hidden></p>');
  return after(html, '<script type="module" src="app.js"></script>', '\n  <script type="module" src="hiring-preview.mjs"></script>');
}

// Run after the existing same-origin packaging step has pinned the engine.
// The browser reads every deployed asset from Hiring's own origin. At build
// time, mirror the exact shared worker/model version already published to Practice.
export async function packageHiringPreview(dest, {
  source = fileURLToPath(new URL('../assessment-preview/', import.meta.url)), fetchImpl = fetch
} = {}) {
  const target = resolve(dest, 'landing/assessment');
  const html = hiringPreviewHtml(await readFile(resolve(target, 'index.html')));
  const manifest = JSON.parse(await readFile(resolve(source, 'practice-assets.json')));
  const origin = 'https://cookcredit-knife-demo.web.app/assessment-bundles/' + bundleForAssetMap(manifest) + '/';
  for (const [name, expected] of Object.entries(manifest)) {
    if (!/^practice-(?:live|contact-v1)\/(?:[A-Za-z0-9_-]+\/)*[A-Za-z0-9._-]+$/.test(name) ||
        name.split('/').includes('..') || !/^[a-f0-9]{64}$/.test(expected)) throw new Error('Invalid Hiring preview asset');
    const response = await fetchImpl(new URL(name, origin), {
      redirect: 'error', signal: AbortSignal.timeout(90000)
    });
    if (!response.ok) throw new Error('Missing shared blade asset: ' + name);
    const raw = Buffer.from(await response.arrayBuffer());
    if (digest(raw) !== expected) throw new Error('Invalid Hiring preview asset digest: ' + name);
    await mkdir(dirname(resolve(target, name)), {recursive:true});
    await writeFile(resolve(target, name), raw);
  }
  for (const name of ['hiring-preview.mjs', 'hiring-preview.css']) {
    const local = await readFile(resolve(source, name), 'utf8');
    await writeFile(resolve(target, name), local.replaceAll('\r\n', '\n'));
  }
  await writeFile(resolve(target, 'index.html'), html);
}
