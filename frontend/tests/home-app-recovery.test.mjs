import test from 'node:test'
import assert from 'node:assert/strict'
import {readFile} from 'node:fs/promises'
import vm from 'node:vm'
import {transformWithEsbuild} from 'vite'

// Execute the real account gate. A successful retry must actually release it.
async function app(api,refreshFailure=false) {
  const states=[],effects=[];let index,tree,queued
  const user={emailVerified:true,async reload(){if(refreshFailure)throw new Error('offline')},async getIdToken(){return 'local-fixture-only'}}
  const auth={currentUser:user}
  const react={lazy:()=> 'lazy-screen',Suspense:'suspense',
    useState(initial){const slot=index++;if(!(slot in states))states[slot]=typeof initial==='function'?initial():initial;
      return [states[slot],value=>{states[slot]=typeof value==='function'?value(states[slot]):value}]},
    useRef(initial){const slot=index++;return states[slot]||={current:initial}},
    useEffect(fn,deps){const slot=index++,old=effects[slot];if(!old||deps.some((d,i)=>d!==old.deps[i]))
      queued.push(()=>{old?.cleanup?.();effects[slot]={deps,cleanup:fn()}})}}
  const jsx=(type,props)=>({type,props})
  const modules={react,'react/jsx-runtime':{jsx,jsxs:jsx,Fragment:'fragment'},
    'firebase/auth':{onAuthStateChanged(_auth,callback){callback(user);return ()=>{}},signOut:async()=>{}},
    '../src/firebase':{auth},'./api':{api}}
  for(const name of ['Account','RequestVisit','Visit','SavedDetails','Enrollment'])modules['./screens/'+name]={__esModule:true,default:name}
  const source=await readFile(new URL('../home/App.jsx',import.meta.url),'utf8')
  const {code}=await transformWithEsbuild(source,'App.jsx',{loader:'jsx',jsx:'automatic',format:'cjs',define:{'import.meta.env':'{"DEV":false}'}})
  const context={module:{exports:{}},require:id=>modules[id]||{},location:{hash:'#team'},
    addEventListener(){},removeEventListener(){},window:{scrollTo(){}}}
  vm.runInNewContext(code,context)
  const Component=context.module.exports.default
  function render(){index=0;queued=[];tree=Component();queued.forEach(fn=>fn())}
  function nodes(node){if(node==null||node===false)return [];if(Array.isArray(node))return node.flatMap(nodes);
    return [node,...nodes(node.props?.children)]}
  const text=()=>nodes(tree).filter(n=>typeof n==='string').join(' ')
  const find=predicate=>nodes(tree).find(n=>n?.props&&predicate(n.props,n))
  async function settle(){await new Promise(resolve=>setImmediate(resolve));render()}
  render();render();await settle();return {render,settle,text,find}
}

test('Home account retry clears a previous API failure and reaches the authorized service desk',async()=>{
  let failed=true,calls=0
  const s=await app(async path=>{assert.equal(path,'/me');calls++;if(failed)throw new Error('Temporary outage');return {operator:true,owner:true}})
  assert.match(s.text(),/Temporary outage/)
  failed=false;await s.find(p=>p.children==='Try again').props.onClick();s.render();await s.settle()
  assert.equal(calls,2);assert.doesNotMatch(s.text(),/couldn’t open|Temporary outage/)
  assert.ok(s.find((p,n)=>n.type==='lazy-screen'&&p.profile?.owner===true))
})

test('Home account retry reports an identity refresh failure without an unhandled rejection',async()=>{
  const s=await app(async()=>{throw new Error('Temporary outage')},true)
  await s.find(p=>p.children==='Try again').props.onClick();s.render()
  assert.match(s.text(),/could not refresh your sign-in/)
  assert.ok(s.find(p=>p.children==='Try again'))
})
