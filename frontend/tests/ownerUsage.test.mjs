import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import vm from 'node:vm'
import { transformWithEsbuild } from 'vite'

async function render(states, call = async () => ({})) {
  const source = await readFile(new URL('../src/components/OwnerUsage.jsx', import.meta.url), 'utf8')
  const { code } = await transformWithEsbuild(source, 'OwnerUsage.jsx', { loader: 'jsx', jsx: 'automatic', format: 'cjs' })
  const effects = []
  const updates = []
  const jsx = (type, props) => ({ type, props })
  let index = 0
  const context = { module: { exports: {} }, require: name => name === 'react' ? {
    useState: () => { const i = index++; return [states[i], value => updates.push([i, value])] },
    useEffect: effect => effects.push(effect),
  } : { jsx, jsxs: jsx } }
  vm.runInNewContext(code, context)
  return { tree: context.module.exports.default({ call }), effects, updates }
}

function nodes(tree) {
  if (!tree || typeof tree !== 'object') return []
  if (Array.isArray(tree)) return tree.flatMap(nodes)
  return [tree, ...nodes(tree.props?.children)]
}

test('usage displays zero customer results separately from owner/test activity', async () => {
  const data = { generatedAt: '2026-10-28T12:00:00Z', activityDefinition: 'Recorded actions only.',
    testClassification: 'Other accounts may include unclassified tests.', weeks: [{
      start: '2026-10-21T12:00:00Z', end: '2026-10-28T12:00:00Z',
      other: { activeUsers: 0, signups: 0, applications: 0, completedAssessments: 0 },
      test: { activeUsers: 1, signups: 0, applications: 0, completedAssessments: 0 },
    }] }
  const { tree } = await render([data, false, ''])
  const rows = nodes(tree).filter(n => n.type === 'tbody')[0].props.children
  assert.equal(rows[0].props.children[1].props.children, 0)
  assert.equal(rows[0].props.children[2].props.children, 1)
  assert.equal(rows.length, 4)
  assert.ok(JSON.stringify(tree).includes('unclassified tests'))
  assert.ok(nodes(tree).some(n => n.type === 'th' && n.props.scope === 'row'))
})

test('failed usage request shows an error instead of invented zero results', async () => {
  const { tree } = await render([null, false, 'Service unavailable'])
  assert.ok(nodes(tree).some(n => n.props?.role === 'alert'))
  assert.ok(!nodes(tree).some(n => n.type === 'table'))
})

test('usage loads once on mount and ignores completion after unmount', async () => {
  let resolve
  let calls = 0
  const { effects, updates } = await render([null, false, ''], path => {
    assert.equal(path, '/usage'); calls++
    return new Promise(done => { resolve = done })
  })
  const cleanup = effects[0]()
  cleanup(); resolve({ weeks: [] })
  await new Promise(done => setImmediate(done))
  assert.equal(calls, 1)
  assert.equal(updates.length, 0)
})
