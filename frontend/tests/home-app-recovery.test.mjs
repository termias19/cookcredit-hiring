import test from 'node:test'
import assert from 'node:assert/strict'
import {readFile} from 'node:fs/promises'
import vm from 'node:vm'
import {transformWithEsbuild} from 'vite'
import {safeHomeRoute} from '../home/navigation.js'

// Execute the real account gate. A successful retry must actually release it.
async function app(api,refreshFailure=false,options={}) {
  const states=[],effects=[];let index,tree,queued,authChanged
  const user=options.signedOut?null:{email:'fixture@example.test',emailVerified:true,async reload(){if(refreshFailure)throw new Error('offline')},async getIdToken(){return 'local-fixture-only'}}
  const auth={currentUser:user},listeners=new Map()
  const react={lazy:()=> 'lazy-screen',Suspense:'suspense',
    useState(initial){const slot=index++;if(!(slot in states))states[slot]=typeof initial==='function'?initial():initial;
      return [states[slot],value=>{states[slot]=typeof value==='function'?value(states[slot]):value}]},
    useRef(initial){const slot=index++;return states[slot]||={current:initial}},
    useEffect(fn,deps){const slot=index++,old=effects[slot];if(!old||deps.some((d,i)=>d!==old.deps[i]))
      queued.push(()=>{old?.cleanup?.();effects[slot]={deps,cleanup:fn()}})}}
  const jsx=(type,props,key)=>({type,props,key})
  const modules={react,'react/jsx-runtime':{jsx,jsxs:jsx,Fragment:'fragment'},
    'firebase/auth':{onAuthStateChanged(_auth,callback){authChanged=callback;callback(user);return ()=>{}},signOut:async()=>{
      if(options.signOutFailure)throw new Error('offline');auth.currentUser=null;authChanged(null)
    }},
    '../src/firebase':{auth},'./api':{api},'./navigation':{safeHomeRoute}}
  for(const name of ['Account','RequestVisit','Visit','SavedDetails','Enrollment'])modules['./screens/'+name]={__esModule:true,default:name}
  const source=await readFile(new URL('../home/App.jsx',import.meta.url),'utf8')
  const {code}=await transformWithEsbuild(source,'App.jsx',{loader:'jsx',jsx:'automatic',format:'cjs',define:{'import.meta.env':'{"DEV":false}'}})
  const context={module:{exports:{}},require:id=>modules[id]||{},URLSearchParams,location:{hash:options.route||'#team'},
    addEventListener(name,fn){listeners.set(name,fn)},removeEventListener(name){listeners.delete(name)},window:{scrollTo(){}}}
  vm.runInNewContext(code,context)
  const Component=context.module.exports.default
  function render(){index=0;queued=[];tree=Component();queued.forEach(fn=>fn())}
  function nodes(node){if(node==null||node===false)return [];if(Array.isArray(node))return node.flatMap(nodes);
    return [node,...nodes(node.props?.children)]}
  const text=()=>nodes(tree).filter(n=>typeof n==='string').join(' ')
  const find=predicate=>nodes(tree).find(n=>n?.props&&predicate(n.props,n))
  async function settle(){await new Promise(resolve=>setImmediate(resolve));render()}
  render();render();await settle();return {render,settle,text,find,location:context.location,
    navigate(hash){context.location.hash=hash;listeners.get('hashchange')?.();render()}}
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

test('private Home rejection identifies the signed-in account and switching preserves the requested destination',async()=>{
  let calls=0
  const s=await app(async()=>{calls++;throw Object.assign(new Error('Private acceptance account required'),{code:'private_acceptance'})})
  assert.match(s.text(),/sign-in worked/);assert.match(s.text(),/fixture@example.test/)
  assert.ok(s.find(p=>p.href==='#help'));assert.ok(s.find(p=>p.href==='#home'))
  await s.find(p=>p.children==='Use a different account').props.onClick();s.render()
  assert.equal(s.location.hash,'team')
  const account=s.find((p,n)=>n.type==='Account')
  assert.ok(account);assert.equal(account.props.next,'team');assert.equal(account.props.user,null)
  assert.equal(calls,1)
})

test('failed account switching stays recoverable and does not invent a signed-out session',async()=>{
  const s=await app(async()=>{throw new Error('Account unavailable')},false,{signOutFailure:true})
  await s.find(p=>p.children==='Use a different account').props.onClick();s.render()
  assert.match(s.text(),/could not sign you out/)
  assert.match(s.text(),/fixture@example.test/)
  assert.equal(s.location.hash,'#team')
  assert.ok(s.find(p=>p.children==='Use a different account'))
})

test('Help and callback remain reachable after account rejection and use separate page instances',async()=>{
  let calls=0
  const s=await app(async()=>{calls++;throw Object.assign(new Error('Private acceptance account required'),{code:'private_acceptance'})})
  s.navigate('#help')
  const help=s.find((p,n)=>typeof n.type==='function'&&n.type.name==='Help')
  assert.ok(help)
  s.navigate('#callback')
  const callback=s.find((p,n)=>typeof n.type==='function'&&n.type.name==='Help')
  assert.ok(callback)
  // React remounts the actual form when these route keys differ.
  assert.notEqual(help.key,callback.key)
  assert.equal(calls,1)
})

test('a public Help link with tracking parameters opens without signing in or loading a private account',async()=>{
  const s=await app(async()=>assert.fail('Public help must not load an account'),false,{signedOut:true,route:'#help?source=email'})
  assert.ok(s.find((p,n)=>typeof n.type==='function'&&n.type.name==='Help'))
  assert.doesNotMatch(s.text(),/Opening your account|Checking your account/)
})

test('signing in from callback recovery preserves that exact internal destination',async()=>{
  const s=await app(async()=>assert.fail('Signed-out recovery must not load an account'),false,
    {signedOut:true,route:'#sign-in?next=callback'})
  assert.equal(s.find((p,n)=>n.type==='Account').props.next,'callback')
})
