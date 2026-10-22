import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import vm from 'node:vm'
import { transformWithEsbuild } from 'vite'

// Render the real screen with its independently loaded report and an empty or
// stale workspace cache, as happens after a direct link or provider refresh.
test('candidate review renders the authorized report without a cached role', async () => {
  const source = await readFile(new URL('../src/screens/BusinessCandidateScreen.jsx', import.meta.url), 'utf8')
  const { code } = await transformWithEsbuild(source, 'BusinessCandidateScreen.jsx', { loader: 'jsx', jsx: 'automatic', format: 'cjs' })
  for (const cachedRole of [null, { title: 'Old cached title' }]) {
    const report = {
      candidate: { id: 'candidate', name: 'Controlled Cook', resumePoints: [] },
      role: { id: 'role', title: 'Private chef' },
      assessment: { deviceEstimates: { overall: 40 } },
      match: { band: 'Review', total: 0.5, gates: { passed: true }, requirements: [] },
    }
    const jsx = (type, props) => ({ type, props })
    const modules = {
      react: { useState: initial => [initial === null ? report : initial, () => {}], useEffect: () => {} },
      'react/jsx-runtime': { jsx, jsxs: jsx, Fragment: 'fragment' },
      'react-router-dom': { useParams: () => ({ id: 'candidate' }), useNavigate: () => () => {}, useSearchParams: () => [new URLSearchParams('role=role')] },
      'framer-motion': { motion: new Proxy({}, { get: (_, tag) => tag }) },
      'lucide-react': {},
      '../context/AuthContext': { useAuth: () => ({ user: {} }) },
      '../context/BusinessContext': { useBusiness: () => ({ roleById: () => cachedRole }) },
      '../utils/match': { reconcileClaims: () => [] },
      '../utils/accreditation': { credentialDetails: () => [] },
      '../data/culinaryTaxonomy': {},
      '../styles/motion': { staggerContainer: () => ({}) },
    }
    const context = { module: { exports: {} }, require: name => modules[name] || {} }
    vm.runInNewContext(code, context)
    const screen = context.module.exports.default()
    const rendered = screen.type(screen.props)
    const text = JSON.stringify(rendered)
    assert.ok(text.includes('Private chef'), 'match must use the role returned with this report')
    assert.ok(text.includes('Watch '), 'the recording action remains available')
    assert.ok(!text.includes('Old cached title'), 'a stale workspace role must not override the report')
  }
})
