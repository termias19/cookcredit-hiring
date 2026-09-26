import test from 'node:test'
import assert from 'node:assert/strict'
import { hiringFirebaseConfig, sharedHiringAuthSource } from '../scripts/copy-hiring-assessment.mjs'

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
