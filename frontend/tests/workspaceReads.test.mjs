import test from 'node:test'
import assert from 'node:assert/strict'
import { workspaceReads } from '../src/utils/workspaceReads.js'

test('settings do not request candidate, shortlist or unrelated role data', () => {
  for (const section of ['company', 'team', 'billing']) assert.deepEqual(workspaceReads('/business/profile', '?section='+section), {roles:false,candidates:false,shortlist:false})
  assert.deepEqual(workspaceReads('/business/profile', '?section=integrations'), {roles:true,candidates:false,shortlist:false})
})
test('role lists avoid roster reads while review and saved views retain them', () => {
  for (const path of ['/business/roles', '/business/role/new', '/business/role/123/edit']) assert.deepEqual(workspaceReads(path), {roles:true,candidates:false,shortlist:false})
  for (const path of ['/business/role/123', '/business/candidates', '/business/candidate/123', '/business/shortlists']) assert.deepEqual(workspaceReads(path), {roles:true,candidates:true,shortlist:true})
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
