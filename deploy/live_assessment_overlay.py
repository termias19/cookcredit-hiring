"""Prepare a hiring-only overlay from the pinned PUBLISHED assessment.

Reuses the engine's existing hiring bridge. It never builds the engine checkout.
Publishing adds /hiring/ while preserving every existing live path and hash.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
import copy

import requests
from hiring_staging import api, client
from hiring_capture_overlay import apply_capture, capture_module
from hiring_readiness_overlay import apply_readiness
from hiring_presentation_overlay import apply_presentation
from hiring_original_landmarks_overlay import apply_original_landmarks

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT.parent / 'work/live-hiring-overlay'
ENGINE = Path('C:/Users/Ermias A/cookcredit-engine/web')
SITE = 'cookcredit-knife-demo'
BASE_VERSION = 'sites/cookcredit-knife-demo/versions/2955becd1bcc829e'
API = 'https://firebasehosting.googleapis.com/v1beta1/'
FILES = ('app.js', 'cloud-library.mjs', 'index.html', 'style.css')
HIRING_API = 'https://cookcredit-hiring-staging-915097816203.us-central1.run.app'


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError('Published baseline changed: '+old[:65])
    return text.replace(old, new, 1)


def block(text, start, end):
    return text[text.index(start):text.index(end, text.index(start))]


def prepare():
    session = client()
    release = api(session, 'GET', API+f'sites/{SITE}/releases', params={'pageSize': 1})['releases'][0]
    if release['version']['name'] != BASE_VERSION:
        previous = json.loads((WORK/'manifest.json').read_text()) if (WORK/'manifest.json').exists() else {}
        if not previous.get('published') or previous.get('release') != release['name']:
            raise RuntimeError('The public assessment changed; review the new release before preparing an overlay.')
        live_files = api(session, 'GET', API+release['version']['name']+'/files', params={'pageSize': 1000})
        if {item['path']: item['hash'] for item in live_files['files']} != previous.get('publishedPaths'):
            raise RuntimeError('The previous hiring overlay changed outside this release process')
    version = api(session, 'GET', API+BASE_VERSION)
    listing = api(session, 'GET', API+BASE_VERSION+'/files', params={'pageSize': 1000})
    if listing.get('nextPageToken'):
        raise RuntimeError('Unexpected baseline file count')
    paths = {item['path']: item['hash'] for item in listing['files']}
    if any(path.endswith(('.pem', '.key')) or '..' in path for path in paths):
        raise RuntimeError('Unexpected sensitive or unsafe baseline asset')
    WORK.mkdir(parents=True, exist_ok=True)
    original = {}
    for name in FILES:
        response = requests.get(f'https://{SITE}.web.app/{name}', timeout=30)
        response.raise_for_status()
        original[name] = response.text
        (WORK / ('baseline-'+name)).write_bytes(response.content)
    current_app = (ENGINE/'app.js').read_text(encoding='utf-8')
    app = original['app.js']
    app = replace_once(app, "import {firebaseConfig}", "import {parseHiringContext, submitHiringAssessment, getHiringSession} from './hiring-bridge.mjs';\nimport {firebaseConfig}")
    app = replace_once(app, "const state = {", "const state = {\n  hiring: null, hiringSessionVerified: false, hiringVerificationError: '', hiringSubmitting: false,")
    app = replace_once(app, 'const cloudLibrary =', "let initialHiringContext = null;\nlet hiringContextError = null;\ntry { initialHiringContext = parseHiringContext(location); } catch (error) { hiringContextError = error; }\nconst cloudLibrary =")
    # Only auth/session/navigation functions are reused from the checkout.
    for start, end in [
        ('function refreshStart()', 'function bindSplash()'),
        ('function syncLibraryAuth(', 'async function openLibrary('),
        ('async function signInWithGoogle()', 'async function signOutOfLibrary()'),
    ]:
        app = replace_once(app, block(app, start, end), block(current_app, start, end))
    app = replace_once(app, "opt.addEventListener('click', () => {", "opt.addEventListener('click', () => {\n      if (state.hiring && opt.dataset.mode !== 'test') return;")
    app = replace_once(app, 'if (test && !state.localPreview) bumpTestTrials();',
                       'if (test && !state.localPreview && !state.hiring) bumpTestTrials();')
    app = replace_once(app, '  updateFeedbackReplayAvailability(true);\n}',
                       '  updateFeedbackReplayAvailability(true);\n  configureHiringResultActions();\n}')
    app = replace_once(app, '  state.recordingBlob = null;',
                       "  state.recordingBlob = null;\n  $('hiring-submit-panel').hidden = true;")
    hiring = block(current_app, 'function syncHiringAuthState(', 'function bindCloudLibrary()')
    hiring = hiring.replace('clean recording', 'recording')
    hiring = replace_once(hiring, "  document.body.classList.add('hiring-experience');", """  document.body.classList.add('hiring-experience');
  document.querySelector('.privacy-note').textContent = 'Your recording stays on this device until you choose Submit to application. Signing in connects this attempt to your application; signing in alone does not upload or share a recording.';
  document.querySelector('#library-signed-out p').textContent = 'Sign in with the same CookCredit account used for this application. Signing in does not upload your recording. After the assessment, choose Submit to application to send the selected recording for review.';
""")
    hiring = replace_once(hiring, '    if (!state.cloudAssessmentId) {',
                          '    await verifyHiringAccess();\n    if (!state.hiringSessionVerified) return;\n\n    if (!state.cloudAssessmentId) {')
    hiring = replace_once(hiring, '      idToken,\n    });',
                          '      idToken,\n      appCheckToken: await cloudLibrary.getAppCheckToken(),\n    });')
    app = replace_once(app, 'function bindCloudLibrary()', hiring+'function bindCloudLibrary()')
    app = replace_once(app, '  bindSplash();', '  bindSplash();\n  await configureHiringExperience();')

    library = original['cloud-library.mjs']
    # Preserve only validated hiring parameters across email-link sign-in.
    library = "import {parseHiringContext} from './hiring-bridge.mjs';\n" + library
    preserve = """    const hiring = parseHiringContext(this.environment.location);
    if (hiring) {
      TARGET.searchParams.set('hiringSession', hiring.sessionId);
      TARGET.searchParams.set('apiOrigin', hiring.apiOrigin);
      TARGET.searchParams.set('returnUrl', hiring.returnUrl);
    }
"""
    library = replace_once(library, "    finishUrl.searchParams.set('finishSignIn', '1');",
                           preserve.replace('TARGET', 'finishUrl')+"    finishUrl.searchParams.set('finishSignIn', '1');")
    library = replace_once(library, '    this.environment.history.replaceState({},',
                           preserve.replace('TARGET', 'cleanUrl')+'    this.environment.history.replaceState({},')
    library = replace_once(library, '  async call(name, data = {}) {', '''  async getIdToken(forceRefresh = false) {
    await this.initialize();
    return this.requireUser().getIdToken(forceRefresh);
  }

  async getAppCheckToken() {
    await this.initialize();
    if (!this.appCheck) throw new Error('CookCredit account security is unavailable. Reload and try again.');
    return (await this.sdk.appCheck.getToken(this.appCheck)).token;
  }

  async call(name, data = {}) {''')

    bridge = (ENGINE/'hiring-bridge.mjs').read_text(encoding='utf-8')
    # Normalize the new source contract before applying the existing capture layer.
    bridge = replace_once(bridge, 'assessmentId, originalLandmarks, idToken', 'assessmentId, idToken')
    bridge = replace_once(bridge, 'JSON.stringify({ assessmentId, ...(originalLandmarks ? {originalLandmarks} : {}) })', 'JSON.stringify({ assessmentId })')
    bridge = replace_once(bridge, "  'https://api.cookcredit.com',", "  'https://api.cookcredit.com',\n  'https://cookcredit-hiring-staging-915097816203.us-central1.run.app',")
    bridge = replace_once(bridge, "  'https://www.cookcredit.com',", "  'https://www.cookcredit.com',\n  'https://cookcredit-hiring-staging.web.app',")
    bridge = replace_once(bridge, 'assessmentId, idToken, fetchImpl = fetch', 'assessmentId, idToken, appCheckToken, fetchImpl = fetch')
    bridge = replace_once(bridge, "        'Content-Type': 'application/json',", "        'Content-Type': 'application/json',\n        'X-Firebase-AppCheck': appCheckToken || '',")
    bridge = bridge.replace('await fetchImpl(', 'await fetchBounded(fetchImpl, ')
    bridge += '''
async function fetchBounded(fetchImpl, url, options) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 180000);
  try { return await fetchImpl(url, {...options, signal: controller.signal}); }
  finally { clearTimeout(timer); }
}
'''
    html = original['index.html']
    current_html = (ENGINE/'index.html').read_text(encoding='utf-8')
    for element, anchor in [('hiring-context-banner', '    <div class="mode-seg"'),
                            ('hiring-submit-panel', '          <button id="btn-delete-recording"')]:
        match = re.search(r'<section id="'+element+r'".*?</section>', current_html, re.S)
        if not match: raise RuntimeError('Canonical hiring markup missing')
        markup = match[0].replace('One verified attempt, connected to your application.',
                                 'Your knife assessment, connected to your application.')
        html = replace_once(html, anchor, markup+'\n'+anchor)
    css = original['style.css'] + '''
/* Hiring-only account and submission controls; capture styling is unchanged. */
.hiring-context-banner,.hiring-submit-panel {border:1px solid #d8d1c7;background:#faf7f0;padding:20px;margin:20px 0;color:#2e2823;}
.hiring-context-banner[hidden],.hiring-submit-panel[hidden] {display:none;}
.hiring-auth-row {display:flex;flex-wrap:wrap;align-items:center;gap:12px;font-size:14px;}
.hiring-context-banner h2,.hiring-submit-panel h3 {margin:0 0 10px;}
.hiring-context-banner p,.hiring-submit-panel p {line-height:1.6;}
'''
    app, html, css = apply_presentation(app, html, css)
    app = apply_readiness(app)
    app, bridge = apply_capture(app, bridge)
    app, bridge = apply_original_landmarks(app, bridge)
    modified = {'landmark-capture.mjs': (ENGINE/'landmark-capture.mjs').read_text(encoding='utf-8'), 'hiring-capture.mjs': capture_module(), 'app.js': app, 'cloud-library.mjs': library, 'hiring-bridge.mjs': bridge, 'index.html': html, 'style.css': css}
    for name, contents in modified.items():
        (WORK/name).write_text(contents, encoding='utf-8', newline='\n')
        if name.endswith(('.js', '.mjs')):
            subprocess.run(['node', '--check', str(WORK/name)], check=True, capture_output=True)
    # The live detector, score formula, recorder and models are copied by their
    # immutable Hosting hashes, never from a newer checkout.
    manifest = {'baseVersion': BASE_VERSION, 'baseRelease': release['name'],
                'expectedLiveVersion': release['version']['name'],
                'config': version.get('config', {}), 'originalPaths': paths,
                'baselineContent': {name: hashlib.sha256((WORK/('baseline-'+name)).read_bytes()).hexdigest() for name in FILES},
                'modified': {name: hashlib.sha256(content.encode()).hexdigest() for name, content in modified.items()},
                'protected': {path: paths[path] for path in ['/wrist.js', '/score.js', '/recording.mjs']},
                'prefix': '/hiring/', 'published': False}
    (WORK/'manifest.json').write_text(json.dumps(manifest, indent=2))
    print(json.dumps({'prepared': True, 'baseVersion': BASE_VERSION, 'baselineFiles': len(paths),
                      'changedOverlayFiles': list(modified), 'existingLivePathsChanged': 0}))


def check_artifacts():
    manifest = json.loads((WORK/'manifest.json').read_text())
    if manifest['baseVersion'] != BASE_VERSION or manifest['prefix'] != '/hiring/':
        raise RuntimeError('Unexpected overlay manifest')
    for name, digest in manifest['modified'].items():
        if name not in (*FILES, 'hiring-bridge.mjs', 'hiring-capture.mjs', 'landmark-capture.mjs') or hashlib.sha256((WORK/name).read_bytes()).hexdigest() != digest:
            raise RuntimeError('Prepared overlay changed; prepare and test it again')
    return manifest


def check_current(session, manifest):
    release = api(session, 'GET', API+f'sites/{SITE}/releases', params={'pageSize': 1})['releases'][0]
    if release['name'] != manifest['baseRelease'] or release['version']['name'] != manifest.get('expectedLiveVersion', BASE_VERSION):
        raise RuntimeError('Live release changed; refusing to overwrite another deployment')
    for name, digest in manifest['baselineContent'].items():
        response = requests.get(f'https://{SITE}.web.app/{name}', timeout=30)
        response.raise_for_status()
        if hashlib.sha256(response.content).hexdigest() != digest:
            raise RuntimeError('Public baseline bytes changed: '+name)


def test():
    manifest = check_artifacts()
    # Run the canonical bridge's behavioral cases against this prepared module.
    # Its checkout-specific source-string assertion is deliberately excluded.
    source = (ENGINE.parent/'tests/web_hiring_bridge.test.mjs').read_text(encoding='utf-8')
    source = source[:source.index("test('the live assessment keeps scoring separate")]
    source = source.replace("'../web/hiring-bridge.mjs'", "'./hiring-bridge.mjs'")
    (WORK/'bridge-behavior.test.mjs').write_text(source, encoding='utf-8')
    subprocess.run(['node', str(WORK/'bridge-behavior.test.mjs')], check=True)
    subprocess.run(['node', str(ROOT/'deploy/tests/live_assessment_bridge.test.mjs'), str(WORK)], check=True)
    subprocess.run(['node', str(ROOT/'deploy/tests/hiring_capture.test.mjs'), str(WORK/'app.js')], check=True)
    manifest['testsPassed'] = True
    (WORK/'manifest.json').write_text(json.dumps(manifest, indent=2))


def publish():
    manifest = check_artifacts()
    if not manifest.get('testsPassed') or manifest.get('published'):
        raise RuntimeError('A fresh tested overlay is required')
    session = client()
    check_current(session, manifest)
    paths = dict(manifest['originalPaths'])
    for path, digest in manifest['originalPaths'].items():
        if not path.startswith('/__/'):
            paths['/hiring'+path] = digest
    blobs = {}
    for name in manifest['modified']:
        compressed = gzip.compress((WORK/name).read_bytes(), mtime=0)
        digest = hashlib.sha256(compressed).hexdigest()
        blobs[digest] = compressed
        paths['/hiring/'+name] = digest
    if any(paths.get(path) != digest for path, digest in manifest['originalPaths'].items()):
        raise RuntimeError('Original live paths must be unchanged')
    config = copy.deepcopy(manifest['config'])
    csp = next(entry['headers']['Content-Security-Policy'] for entry in config['headers']
               if entry.get('glob') == '**' and 'Content-Security-Policy' in entry['headers'])
    csp = replace_once(csp, "connect-src 'self'", "connect-src 'self' "+HIRING_API)
    csp = replace_once(csp, "img-src 'self'", "img-src 'self' "+HIRING_API+"/api/business/branding/")
    # Firebase applies the last matching header. Only the new prefix may call
    # the staging API; existing root routes retain their original policy.
    config['headers'].append({'glob': '/hiring/**', 'headers': {
        'Content-Security-Policy': csp, 'X-Robots-Tag': 'noindex, nofollow',
        'Cache-Control': 'no-cache, max-age=0, must-revalidate'}})
    version = api(session, 'POST', API+f'sites/{SITE}/versions', json={'config': config})
    manifest['preparedVersion'] = version['name']
    (WORK/'manifest.json').write_text(json.dumps(manifest, indent=2))
    population = api(session, 'POST', API+version['name']+':populateFiles', json={'files': paths})
    required = population.get('uploadRequiredHashes', [])
    if any(digest not in blobs for digest in required):
        raise RuntimeError('Hosting did not reuse all immutable baseline assets; no release was published')
    upload = population['uploadUrl']
    if not upload.startswith('https://upload-firebasehosting.googleapis.com/upload/sites/'+SITE+'/'):
        raise RuntimeError('Unexpected upload destination')
    for digest in required:
        response = session.post(upload+'/'+digest, data=blobs[digest],
                                headers={'Content-Type': 'application/octet-stream'}, timeout=60)
        response.raise_for_status()
    api(session, 'PATCH', API+version['name'], params={'updateMask': 'status'}, json={'status': 'FINALIZED'})
    listing = api(session, 'GET', API+version['name']+'/files', params={'pageSize': 1000})
    stored = {item['path']: item['hash'] for item in listing['files']}
    if stored != paths or listing.get('nextPageToken'):
        raise RuntimeError('Finalized Hosting version did not preserve the exact requested paths')
    check_current(session, manifest)
    release = api(session, 'POST', API+f'sites/{SITE}/releases', params={'versionName': version['name']},
                  json={'message': 'Add tested hiring-only prefix; preserve all 31 published assessment paths and hashes'})
    manifest.update(published=True, release=release['name'], publishedPaths=paths,
                    rollbackVersion=BASE_VERSION, existingLivePathsChanged=0)
    (WORK/'manifest.json').write_text(json.dumps(manifest, indent=2))
    print(json.dumps({'url': f'https://{SITE}.web.app/hiring/', 'release': release['name'],
                      'existingLivePathsChanged': 0, 'bridgeEnabled': False}))


def verify():
    manifest = check_artifacts()
    if not manifest.get('published'):
        raise RuntimeError('No overlay release has been published')
    session = client()
    release = api(session, 'GET', API+f'sites/{SITE}/releases', params={'pageSize': 1})['releases'][0]
    if release['name'] != manifest['release']:
        raise RuntimeError('A newer release exists; inspect it before verification')
    listing = api(session, 'GET', API+release['version']['name']+'/files', params={'pageSize': 1000})
    stored = {item['path']: item['hash'] for item in listing['files']}
    if stored != manifest['publishedPaths']:
        raise RuntimeError('Published asset hashes differ')
    for path, digest in manifest['originalPaths'].items():
        if stored[path] != digest:
            raise RuntimeError('An original asset changed')
    root = requests.get(f'https://{SITE}.web.app/', timeout=30)
    overlay = requests.get(f'https://{SITE}.web.app/hiring/', timeout=30)
    root.raise_for_status(); overlay.raise_for_status()
    if hashlib.sha256(root.content).hexdigest() != manifest['baselineContent']['index.html']:
        raise RuntimeError('Live root content changed')
    if hashlib.sha256(overlay.content).hexdigest() != manifest['modified']['index.html']:
        raise RuntimeError('Hiring route did not serve the prepared assessment')
    if HIRING_API in root.headers.get('Content-Security-Policy', ''):
        raise RuntimeError('Hiring-only CSP leaked onto root')
    if HIRING_API not in overlay.headers.get('Content-Security-Policy', ''):
        raise RuntimeError('Hiring API is blocked by the hiring route CSP')
    for name in manifest['modified']:
        response = requests.get(f'https://{SITE}.web.app/hiring/{name}', timeout=30)
        response.raise_for_status()
        if hashlib.sha256(response.content).hexdigest() != manifest['modified'][name]:
            raise RuntimeError('Hiring artifact does not match: '+name)
    manifest['publicHttpVerified'] = True
    (WORK/'manifest.json').write_text(json.dumps(manifest, indent=2))
    print(json.dumps({'publicHttpVerified': True, 'originalAssetsUnchanged': len(manifest['originalPaths']),
                      'hiringArtifactsVerified': len(manifest['modified']), 'cspScoped': True}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['prepare', 'test', 'publish', 'verify'])
    args = parser.parse_args()
    globals()[args.phase]()
