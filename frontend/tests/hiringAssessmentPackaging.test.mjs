import test from 'node:test'
import assert from 'node:assert/strict'
import { hiringFirebaseConfig, sharedHiringAuthSource, hiringBridgeSource } from '../scripts/copy-hiring-assessment.mjs'
import { readFile } from 'node:fs/promises'
import { createHash } from 'node:crypto'

const originalBridge = (await readFile(new URL('./fixtures/published-assessment/hiring-bridge.mjs', import.meta.url), 'utf8')).replaceAll('\r\n', '\n')
const manifest = JSON.parse(await readFile(new URL('../scripts/hiring-assessment-release.json', import.meta.url)))
const production = { VITE_DEPLOYMENT_ENVIRONMENT: 'production', VITE_API_URL: 'https://cookcredit-hiring-915097816203.us-central1.run.app', VITE_AUTH_EMAIL_CONTINUE_URL: 'https://hiring.cookcredit.com/login' }
const staging = { VITE_DEPLOYMENT_ENVIRONMENT: 'staging', VITE_API_URL: 'https://cookcredit-hiring-staging-915097816203.us-central1.run.app', VITE_AUTH_EMAIL_CONTINUE_URL: 'https://cookcredit-hiring-staging.web.app/login' }
const id = '123e4567-e89b-42d3-a456-426614174000'
function launch(env, overrides = {}) {
  const origin = new URL(env.VITE_AUTH_EMAIL_CONTINUE_URL).origin
  return new URL(`${origin}/landing/assessment/?` + new URLSearchParams({ mode: 'test', hiringSession: id, apiOrigin: env.VITE_API_URL, returnUrl: `${origin}/application-assessment-return/${id}`, ...overrides }))
}
const bridgeModule = source => import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`)

test('published bridge fixture matches pinned release and reproduces the production failure', async () => {
  assert.equal(createHash('sha256').update(originalBridge).digest('hex'), manifest.files['/hiring/hiring-bridge.mjs'].sha256)
  const bridge = await bridgeModule(originalBridge)
  assert.throws(() => bridge.parseHiringContext(launch(production)), /API address is not approved/)
})

test('packaged bridge accepts the generated production and staging links only in their own deployment', async () => {
  for (const env of [production, staging]) {
    const bridge = await bridgeModule(hiringBridgeSource(originalBridge, env))
    assert.deepEqual(bridge.parseHiringContext(launch(env)), {sessionId:id, apiOrigin:env.VITE_API_URL, returnUrl:new URL(env.VITE_AUTH_EMAIL_CONTINUE_URL).origin + `/application-assessment-return/${id}`, mode:'test'})
    assert.throws(() => bridge.parseHiringContext(launch(env === production ? staging : production)), /not approved/)
    for (const apiOrigin of ['https://attacker.invalid', env.VITE_API_URL + '.evil.test', env.VITE_API_URL + '/path', env.VITE_API_URL + '?token=x', 'http://localhost:5000', env.VITE_API_URL.replace('https://', 'https://user:pass@')]) {
      assert.throws(() => bridge.parseHiringContext(launch(env, {apiOrigin})))
    }
    const returnUrl = new URL(env.VITE_AUTH_EMAIL_CONTINUE_URL).origin + `/application-assessment-return/${id}`
    for (const value of [returnUrl + '?x=1', returnUrl + '#x', returnUrl.replace(id, 'another-session'), returnUrl.replace('.com/', '.com.evil.test/').replace('.app/', '.app.evil.test/')]) {
      assert.throws(() => bridge.parseHiringContext(launch(env, {returnUrl:value})))
    }
  }
})

test('packaging fails closed for mismatched configuration or changed bridge anchors', () => {
  for (const env of [{}, {...production,VITE_API_URL:staging.VITE_API_URL}, {...production,VITE_AUTH_EMAIL_CONTINUE_URL:staging.VITE_AUTH_EMAIL_CONTINUE_URL}]) {
    assert.throws(() => hiringBridgeSource(originalBridge, env), /deployment addresses/)
  }
  assert.throws(() => hiringBridgeSource(originalBridge.replace('const DEFAULT_API_ORIGINS', 'const CHANGED_ORIGINS'), production), /allowlist changed/)
})

test('assessment shares the hiring auth identity but retains original recording storage', () => {
  const original = { projectId:'shared-project', apiKey:'engine-key',appId:'engine-app',storageBucket:'engine-recordings',functionsRegion:'us-central1' }
  const env = { VITE_FIREBASE_PROJECT_ID:'shared-project',VITE_FIREBASE_API_KEY:'hiring-key',VITE_FIREBASE_APP_ID:'hiring-app',VITE_FIREBASE_AUTH_DOMAIN:'shared.firebaseapp.com',VITE_RECAPTCHA_ENTERPRISE_SITE_KEY:'hiring-site-key' }
  const result = hiringFirebaseConfig(original,env)
  assert.equal(result.apiKey,'hiring-key')
  assert.equal(result.appId,'hiring-app')
  assert.equal(result.storageBucket,'engine-recordings')
  assert.equal(result.functionsRegion,'us-central1')
  assert.equal(original.apiKey,'engine-key')
  assert.throws(()=>hiringFirebaseConfig(original,{...env,VITE_FIREBASE_PROJECT_ID:'different'}))
  assert.throws(()=>hiringFirebaseConfig(original,{...env,VITE_RECAPTCHA_ENTERPRISE_SITE_KEY:''}))
})


test('same-origin assessment retains the existing Firebase persistence instead of signing another tab out', () => {
  const original = '    await this.sdk.auth.setPersistence(this.auth, this.sdk.auth.browserLocalPersistence);'
  const source = 'before();\n' + original + '\nafter();'
  assert.equal(sharedHiringAuthSource(source), 'before();\n    await this.auth.authStateReady(); // Retain the hiring app persistence across tabs.\nafter();')
  assert.throws(() => sharedHiringAuthSource('changed initialization'), /initialization changed/)
  assert.throws(() => sharedHiringAuthSource(original + original), /initialization changed/)
})
