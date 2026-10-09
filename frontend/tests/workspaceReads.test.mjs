import test from 'node:test'
import assert from 'node:assert/strict'
import { workspaceReads } from '../src/utils/workspaceReads.js'

test('settings do not request candidate, shortlist or unrelated role data', () => {
  for (const section of ['company', 'team', 'billing']) assert.deepEqual(workspaceReads('/business/profile', '?section='+section), {roles:false,candidates:false,shortlist:false})
  assert.deepEqual(workspaceReads('/business/profile', '?section=integrations'), {roles:true,candidates:false,shortlist:false})
})
test('role lists avoid roster reads while review and saved views retain them', () => {
  for (const path of ['/business/roles', '/business/role/new', '/business/role/123/edit']) assert.deepEqual(workspaceReads(path), {roles:true,candidates:false,shortlist:false})
  for (const path of ['/business/role/123', '/business/candidate/123', '/business/shortlists']) assert.deepEqual(workspaceReads(path), {roles:true,candidates:true,shortlist:true})
  assert.deepEqual(workspaceReads('/business/candidates'), {roles:false,candidates:true,shortlist:true})
  assert.deepEqual(workspaceReads('/business/candidates', '?view=saved'), {roles:false,candidates:true,shortlist:true})
})


import { readFile } from 'node:fs/promises'
import vm from 'node:vm'
import { transformWithEsbuild } from 'vite'

test('actual provider makes one settings request, two integration requests and four review requests', async () => {
  const source = await readFile(new URL('../src/context/BusinessContext.jsx',import.meta.url),'utf8')
  const {code} = await transformWithEsbuild(source,'BusinessContext.jsx',{loader:'jsx',jsx:'automatic',format:'cjs'})
  for (const [pathname,search,expected] of [
    ['/business/profile','?section=team',['org']],
    ['/business/profile','?section=integrations',['org','roles']],
    ['/business/roles','',['org','roles']],
    ['/business/candidates','',['org','shortlist','candidates']],
    ['/business/candidates','?view=saved',['org','shortlist','candidates']],
    ['/business/role/123','',['org','roles','shortlist','candidates']],
  ]) {
    const calls=[]
    const api={}
    for (const [name,label] of [['getBusinessOrg','org'],['getBusinessRoles','roles'],['getBusinessShortlist','shortlist'],['getBusinessCandidates','candidates']]) api[name]=async()=>{calls.push(label);return {}}
    const react={createContext:()=>({Provider:'provider'}),useContext:()=>null,useRef:initial=>({current:initial}),useState:initial=>[initial,()=>{}],useCallback:fn=>fn,useEffect:fn=>fn()}
    const modules={'react':react,'react/jsx-runtime':{jsx:()=>null},'react-router-dom':{useLocation:()=>({pathname,search})},'./AuthContext':{useAuth:()=>({user:{getIdToken:async()=>'fixture'}})},'../utils/workspaceReads':{workspaceReads},'../utils/Api':api}
    const context={module:{exports:{}},require:name=>modules[name]}
    vm.runInNewContext(code,context)
    context.module.exports.BusinessProvider({children:null})
    await new Promise(resolve=>setImmediate(resolve))
    assert.deepEqual(calls,expected)
  }
})


test('first star immediately loads a pending applicant into the saved list; refresh failure does not undo a saved star', async () => {
  const source = await readFile(new URL('../src/context/BusinessContext.jsx', import.meta.url), 'utf8')
  const { code } = await transformWithEsbuild(source, 'BusinessContext.jsx', { loader: 'jsx', jsx: 'automatic', format: 'cjs' })
  for (const failRefresh of [false, true]) {
    const slots = []; let index = 0, writes = 0
    const useState = initial => { const slot=index++; if (!(slot in slots)) slots[slot]=initial; return [slots[slot], next=>{slots[slot]=typeof next==='function'?next(slots[slot]):next}] }
    const react = { createContext:()=>({Provider:'provider'}), useContext:()=>null, useState,
      useRef: initial=>useState({current:initial})[0], useCallback:fn=>fn, useEffect:()=>{} }
    const api = { toggleBusinessShortlist:async()=>{writes++; return {shortlisted:true}},
      getBusinessShortlist:async()=>{if(failRefresh) throw Error('offline'); return {candidates:[{id:'pending',name:'Pending Applicant',hasVideo:false}]}} }
    const modules={'react':react,'react/jsx-runtime':{jsx:(_,props)=>props},'react-router-dom':{useLocation:()=>({pathname:'/business/role/123',search:''})},'./AuthContext':{useAuth:()=>({user:{getIdToken:async()=>'fixture'}})},'../utils/workspaceReads':{workspaceReads},'../utils/Api':api}
    const context={module:{exports:{}},require:name=>modules[name]}; vm.runInNewContext(code,context)
    const render=()=>{index=0;return context.module.exports.BusinessProvider({children:null}).value}
    const first=render(); assert.equal(await first.toggleShortlist('pending'),true)
    const saved=render(); assert.equal(saved.isShortlisted('pending'),true); assert.equal(writes,1)
    if(failRefresh) assert.match(saved.actionError,/saved to shortlist/)
    else assert.equal(saved.shortlistCandidates[0].name,'Pending Applicant')
  }
})

test('a failed shortlist read is a recoverable error, never an empty saved list', async () => {
  const source = await readFile(new URL('../src/context/BusinessContext.jsx', import.meta.url), 'utf8')
  const { code } = await transformWithEsbuild(source, 'BusinessContext.jsx', { loader: 'jsx', jsx: 'automatic', format: 'cjs' })
  const writes = []
  const react = { createContext: () => ({ Provider: 'provider' }), useContext: () => null,
    useRef: initial => ({ current: initial }), useState: initial => [initial, value => writes.push(value)],
    useCallback: fn => fn, useEffect: fn => fn() }
  const api = { getBusinessOrg: async () => ({org:{id:'company'}}), getBusinessCandidates: async () => ({candidates:[]}),
    getBusinessShortlist: async () => { throw Error('network unavailable') } }
  const modules = { react, 'react/jsx-runtime': { jsx: () => null },
    'react-router-dom': { useLocation: () => ({ pathname: '/business/candidates', search: '?view=saved' }) },
    './AuthContext': { useAuth: () => ({ user: { getIdToken: async () => 'fixture' } }) },
    '../utils/workspaceReads': { workspaceReads }, '../utils/Api': api }
  const context = { module: { exports: {} }, require: name => modules[name] }
  vm.runInNewContext(code, context)
  context.module.exports.BusinessProvider({ children: null })
  await new Promise(resolve => setImmediate(resolve))
  assert.ok(writes.includes('load'))
  assert.equal(writes.at(-1), false)
})
