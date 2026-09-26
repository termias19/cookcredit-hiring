// Package the pinned published assessment. Never build a second scoring fork.
import { captureFullOverlay, originalEngineRenderer } from './engine-overlay-adapter.mjs'
import { readFile, mkdir, writeFile } from 'node:fs/promises'
import { createHash } from 'node:crypto'
import { resolve, dirname } from 'node:path'
import { pathToFileURL } from 'node:url'

export function hiringFirebaseConfig(original, env) {
  if (original.projectId !== env.VITE_FIREBASE_PROJECT_ID) throw new Error('Assessment and hiring must use the same Firebase project')
  const result = { ...original }
  for (const [key, name] of Object.entries({ apiKey: 'VITE_FIREBASE_API_KEY', appId: 'VITE_FIREBASE_APP_ID', authDomain: 'VITE_FIREBASE_AUTH_DOMAIN', appCheckSiteKey: 'VITE_RECAPTCHA_ENTERPRISE_SITE_KEY' })) {
    if (!env[name]) throw new Error('Missing hiring assessment configuration: ' + name)
    result[key] = env[name]
  }
  // Keep the engine's recording bucket, functions, measurements and formulas.
  return result
}

// The standalone learning page forces localStorage persistence. In the hiring
// origin, both pages must retain Firebase's default persistence; migrating it
// while another tab is open signs that tab out. Only adapt this exact pinned
// authentication line. Scoring stays byte-identical; the separate overlay adapter extends visual capture.
export function sharedHiringAuthSource(source) {
  const original = '    await this.sdk.auth.setPersistence(this.auth, this.sdk.auth.browserLocalPersistence);'
  if (source.split(original).length !== 2) throw new Error('Pinned assessment auth initialization changed')
  return source.replace(original, '    await this.auth.authStateReady(); // Retain the hiring app persistence across tabs.')
}

// Adapt only the pinned bridge's deployment addresses. Never trust a link's
// query parameters to extend the allowlist or change the assessment/scorer.
export function hiringBridgeSource(source, env) {
  const deployments = {
    production: ['https://cookcredit-hiring-915097816203.us-central1.run.app', 'https://hiring.cookcredit.com'],
    staging: ['https://cookcredit-hiring-staging-915097816203.us-central1.run.app', 'https://cookcredit-hiring-staging.web.app'],
  }
  const addresses = deployments[env.VITE_DEPLOYMENT_ENVIRONMENT]
  if (!addresses || env.VITE_API_URL !== addresses[0] || env.VITE_AUTH_EMAIL_CONTINUE_URL !== `${addresses[1]}/login`) {
    throw new Error('Assessment bridge deployment addresses do not match hiring configuration')
  }
  for (const [name, origin] of [['API', addresses[0]], ['RETURN', addresses[1]]]) {
    const pattern = new RegExp(`const DEFAULT_${name}_ORIGINS = Object\\.freeze\\(\\[\\n  \\.\\.\\.PRODUCTION_${name}_ORIGINS,\\n  \\.\\.\\.DEVELOPMENT_${name}_ORIGINS,\\n\\]\\);`, 'g')
    if ([...source.matchAll(pattern)].length !== 1) throw new Error('Pinned assessment bridge allowlist changed')
    source = source.replace(pattern, `const DEFAULT_${name}_ORIGINS = Object.freeze([${JSON.stringify(origin)}]);`)
  }
  return source
}

export async function copyHiringAssessment({ dest = resolve('dist'), env = process.env, fetchImpl = fetch } = {}) {
  const manifest = JSON.parse(await readFile(new URL('./hiring-assessment-release.json', import.meta.url), 'utf8'))
  if (manifest.sourceOrigin !== 'https://cookcredit-knife-demo.web.app') throw new Error('Unexpected assessment source')
  const entries = Object.entries(manifest.files)
  let next = 0
  await Promise.all(Array.from({ length: 4 }, async () => {
    while (next < entries.length) {
      const [path, expected] = entries[next++]
      if (!path.startsWith('/hiring/') || path.includes('..') || !/^[a-zA-Z0-9_./-]+$/.test(path)) throw new Error('Unsafe assessment asset path')
      const response = await fetchImpl(manifest.sourceOrigin + path, { signal: AbortSignal.timeout(90000) })
      if (!response.ok) throw new Error('Assessment download failed: ' + path)
      const bytes = Buffer.from(await response.arrayBuffer())
      if (createHash('sha256').update(bytes).digest('hex') !== expected.sha256) throw new Error('Published assessment changed: ' + path)
      // /landing/ is already excluded by older installed service workers, so
      // existing applicants do not need a manual app update to open this page.
      const target = resolve(dest, 'landing/assessment/' + path.slice('/hiring/'.length))
      await mkdir(dirname(target), { recursive: true }); await writeFile(target, bytes)
    }
  }))
  const appPath = resolve(dest, 'landing/assessment/app.js')
  const capturePath = resolve(dest, 'landing/assessment/landmark-capture.mjs')
  const originalApp = await readFile(appPath, 'utf8')
  const rendererId = manifest.files['/hiring/app.js'].sha256
  const adapted = captureFullOverlay(originalApp, await readFile(capturePath, 'utf8'), rendererId)
  await writeFile(appPath, adapted.app)
  await writeFile(capturePath, adapted.capture)
  await mkdir(resolve(dest, 'assessment-overlays'), { recursive: true })
  await writeFile(resolve(dest, `assessment-overlays/${rendererId}.mjs`), originalEngineRenderer(originalApp))
  const libraryPath = resolve(dest, 'landing/assessment/cloud-library.mjs')
  await writeFile(libraryPath, sharedHiringAuthSource(await readFile(libraryPath, 'utf8')))
  const bridgePath = resolve(dest, 'landing/assessment/hiring-bridge.mjs')
  await writeFile(bridgePath, hiringBridgeSource(await readFile(bridgePath, 'utf8'), env))
  const configPath = resolve(dest, 'landing/assessment/firebase-client-config.mjs')
  const { firebaseConfig } = await import(pathToFileURL(configPath).href)
  const config = hiringFirebaseConfig(firebaseConfig, env)
  await writeFile(configPath, 'export const firebaseConfig = Object.freeze(' + JSON.stringify(config, null, 2) + ');\n')
  console.log(`Packaged ${entries.length} pinned hiring assessment assets; shared sign-in, original recording bucket.`)
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href && process.env.VITE_ASSESSMENT_SAME_ORIGIN === '1') await copyHiringAssessment()
