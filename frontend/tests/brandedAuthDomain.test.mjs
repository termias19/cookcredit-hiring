import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { transformWithEsbuild } from 'vite'
import vm from 'node:vm'

test('Hiring branded auth keeps the existing project and leaves shared assessment config independent', async () => {
  const source = await readFile(new URL('../src/firebase.js', import.meta.url), 'utf8')
  for (const branded of [undefined, 'cookcredit.com']) {
    const env = { VITE_FIREBASE_PROJECT_ID: 'foodnlit-1123e', VITE_FIREBASE_AUTH_DOMAIN: 'foodnlit-1123e.firebaseapp.com', VITE_HIRING_AUTH_DOMAIN: branded }
    const { code } = await transformWithEsbuild(source, 'firebase.js', { format: 'cjs', define: { 'import.meta.env': JSON.stringify(env) } })
    let initialized
    const modules = { 'firebase/app': { initializeApp: config => { initialized=config; return {} }, getApps: () => [] }, 'firebase/auth': { getAuth: () => ({}) } }
    const context = { module: { exports: {} }, require: name => modules[name] }
    vm.runInNewContext(code, context)
    assert.equal(initialized.authDomain, branded || env.VITE_FIREBASE_AUTH_DOMAIN)
    assert.equal(initialized.projectId, 'foodnlit-1123e')
    assert.equal(env.VITE_FIREBASE_AUTH_DOMAIN, 'foodnlit-1123e.firebaseapp.com')
  }
})

test('Hiring CSP permits only the exact branded host, without altering the assessment policy', async () => {
  const config = JSON.parse(await readFile(new URL('../firebase.json', import.meta.url), 'utf8'))
  const hosting = Array.isArray(config.hosting) ? config.hosting : [config.hosting]
  const policies = hosting.flatMap(h => h.headers || []).flatMap(row => (row.headers || []).filter(h => h.key === 'Content-Security-Policy').map(h => ({source:row.source, value:h.value})))
  const main = policies.find(p => p.source === '**')
  assert.ok(main)
  const frames = main.value.split(';').find(d => d.trim().startsWith('frame-src ')).split(/\s+/)
  assert.ok(frames.includes('https://cookcredit.com'))
  assert.ok(!frames.includes('https://*.cookcredit.com'))
  assert.ok(!frames.includes('*'))
})
