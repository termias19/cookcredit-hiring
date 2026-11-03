import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'

const {hosting} = JSON.parse(readFileSync(new URL('../home/firebase.json',import.meta.url),'utf8'))
const headers=Object.fromEntries(hosting.headers.find(row=>row.source==='**').headers.map(row=>[row.key,row.value]))

test('Home staging routes its API before the SPA and pins its own service revision',()=>{
  assert.equal(hosting.site,'cookcredit-home-staging')
  assert.equal(hosting.public,'../dist-home')
  assert.deepEqual(hosting.rewrites[0],{source:'/api/home/**',run:{serviceId:'cookcredit-home-staging',region:'us-central1',pinTag:true}})
  // Home uses hash routes: missing JS must be a404, never the SPA HTML.
  assert.deepEqual(hosting.rewrites[1],{source:'/',destination:'/index.html'})
})

test('Home policy supports branded Google login and protects private navigation',()=>{
  assert.equal(headers['Referrer-Policy'],'no-referrer')
  assert.equal(headers['Cross-Origin-Opener-Policy'],'same-origin-allow-popups')
  assert.match(headers['X-Robots-Tag'],/noindex/)
  assert.match(headers['Permissions-Policy'],/camera=\(\)/)
  const scripts=headers['Content-Security-Policy'].split(';').find(row=>row.trim().startsWith('script-src'))
  assert.match(scripts,/https:\/\/apis\.google\.com/)
  assert.doesNotMatch(scripts,/unsafe-inline|unsafe-eval|\*/)
  assert.match(headers['Content-Security-Policy'],/frame-src https:\/\/cookcredit\.com/)
  assert.doesNotMatch(headers['Content-Security-Policy'],/\*\.run\.app|\*\.firebaseapp\.com/)
})

test('unknown asset responses cannot inherit year-long wildcard caching',()=>{
  assert.equal(headers['Cache-Control'],'no-store')
  assert.ok(hosting.headers.every(row=>row.source==='**'||!row.source.includes('*')))
  // The guarded publisher adds immutable caching for exact manifest paths only.
})

test('Home connect policy permits the installed App Check exchange endpoint without wildcards',()=>{
  const sdk=readFileSync(new URL('../node_modules/@firebase/app-check/dist/esm/index.esm.js',import.meta.url),'utf8')
  const endpoint=new URL(sdk.match(/const BASE_ENDPOINT = '([^']+)'/)[1]).origin
  const connect=headers['Content-Security-Policy'].split(';').find(row=>row.trim().startsWith('connect-src')).trim().split(/\s+/).slice(1)
  assert.equal(endpoint,'https://content-firebaseappcheck.googleapis.com')
  assert.ok(connect.includes(endpoint),'The actual SDK exchange is blocked before it can reach Google')
  assert.ok(connect.every(origin=>!origin.includes('*')))
  assert.ok(connect.includes("'self'"))
})
