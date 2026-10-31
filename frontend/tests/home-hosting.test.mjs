import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'

const {hosting} = JSON.parse(readFileSync(new URL('../home/firebase.json',import.meta.url),'utf8'))
const headers=Object.fromEntries(hosting.headers.find(row=>row.source==='**').headers.map(row=>[row.key,row.value]))

test('Home staging routes its API before the SPA and pins its own service revision',()=>{
  assert.equal(hosting.site,'cookcredit-home-staging')
  assert.equal(hosting.public,'../dist-home')
  assert.deepEqual(hosting.rewrites[0],{source:'/api/home/**',run:{serviceId:'cookcredit-home-staging',region:'us-central1',pinTag:true}})
  assert.deepEqual(hosting.rewrites[1],{source:'**',destination:'/index.html'})
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
