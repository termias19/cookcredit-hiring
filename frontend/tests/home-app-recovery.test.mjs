import test from 'node:test'
import assert from 'node:assert/strict'
import {readFile} from 'node:fs/promises'
import vm from 'node:vm'
import {transformWithEsbuild} from 'vite'
import * as homeNavigation from '../home/navigation.js'
const {safeHomeRoute}=homeNavigation
import * as visitPresentation from '../home/visitPresentation.js'

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
    '../src/firebase':{auth},'./api':{api},'./navigation':homeNavigation,'./visitPresentation':visitPresentation}
  for(const name of ['Account','RequestVisit','Visit','SavedDetails','Enrollment'])modules['./screens/'+name]={__esModule:true,default:name}
  const source=await readFile(new URL('../home/App.jsx',import.meta.url),'utf8')
  const {code}=await transformWithEsbuild(source,'App.jsx',{loader:'jsx',jsx:'automatic',format:'cjs',define:{
    'import.meta.env':JSON.stringify({DEV:false,PROD:options.production===true,VITE_HOME_PRIVATE_ACCEPTANCE:options.privateAcceptance?'1':undefined,
      VITE_HOME_ENROLLMENT_ONLY:options.enrollmentBuild?'1':undefined})}})
  const replacements=[]
  const context={module:{exports:{}},require:id=>modules[id]||{},URLSearchParams,location:{hash:options.route||'#team',replace:url=>replacements.push(url)},
    addEventListener(name,fn){listeners.set(name,fn)},removeEventListener(name){listeners.delete(name)},window:{scrollTo(){}}}
  vm.runInNewContext(code,context)
  const Component=context.module.exports.default
  function render(){index=0;queued=[];tree=Component();queued.forEach(fn=>fn())}
  function nodes(node){if(node==null||node===false)return [];if(Array.isArray(node))return node.flatMap(nodes);
    return [node,...nodes(node.props?.children)]}
  const text=()=>nodes(tree).filter(n=>typeof n==='string').join(' ')
  const find=predicate=>nodes(tree).find(n=>n?.props&&predicate(n.props,n))
  async function settle(){await new Promise(resolve=>setImmediate(resolve));render()}
  render();render();await settle();return {render,settle,text,find,replacements,location:context.location,
    changeUser(next){auth.currentUser=next;authChanged(next);render()},
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

test('Help and legacy callback share one form for the same signed-in identity',async()=>{
  let calls=0
  const s=await app(async()=>{calls++;throw Object.assign(new Error('Private acceptance account required'),{code:'private_acceptance'})})
  s.navigate('#help')
  const help=s.find((p,n)=>typeof n.type==='function'&&n.type.name==='Help')
  assert.ok(help)
  s.navigate('#callback')
  const callback=s.find((p,n)=>typeof n.type==='function'&&n.type.name==='Help')
  assert.ok(callback)
  assert.equal(help.key,callback.key,'An alias must not clear the form or replace its retry request ID')
  s.changeUser({uid:'another-customer',email:'another@example.test',emailVerified:true})
  assert.notEqual(s.find((p,n)=>typeof n.type==='function'&&n.type.name==='Help').key,callback.key,
    'Contact details must not survive a change to another account')
  assert.equal(calls,2,'A different identity requires its own access check')
})

test('a public Help link with tracking parameters opens without signing in or loading a private account',async()=>{
  const s=await app(async()=>assert.fail('Public help must not load an account'),false,{signedOut:true,route:'#help?source=email'})
  assert.ok(s.find((p,n)=>typeof n.type==='function'&&n.type.name==='Help'))
  assert.doesNotMatch(s.text(),/Opening your account|Checking your account/)
  assert.equal(s.find((p,n)=>typeof n.type==='function'&&n.type.name==='Help').props.privateAcceptance,false)
})

test('the explicit private build flag reaches Help without a hostname guess or an account request',async()=>{
  const s=await app(async()=>assert.fail('Signed-out Help must not fetch a private profile'),false,
    {signedOut:true,privateAcceptance:true,route:'#help?source=email'})
  assert.equal(s.find((p,n)=>typeof n.type==='function'&&n.type.name==='Help').props.privateAcceptance,true)
})

test('signing in from callback recovery preserves that exact internal destination',async()=>{
  const s=await app(async()=>assert.fail('Signed-out recovery must not load an account'),false,
    {signedOut:true,route:'#sign-in?next=callback'})
  assert.equal(s.find((p,n)=>n.type==='Account').props.next,'callback')
})

test('authenticated customers get three simple workspace destinations and one arrange action without operator links',async()=>{
  const calls=[]
  const s=await app(async path=>{calls.push(path);return {owner:false,operator:false,helper:false,name:'Synthetic customer'}},false,{route:'#visits'})
  const nav=s.find(p=>p['aria-label']==='Your workspace')
  const nodes=n=>!n||typeof n!=='object'?[]:[n,...(Array.isArray(n.props?.children)?n.props.children:[n.props?.children]).flatMap(nodes)]
  assert.deepEqual(nodes(nav).filter(n=>n.type==='a').map(n=>n.props.href),['#visits','#enroll','#help'])
  assert.equal(s.find(p=>p.href==='#visits').props['aria-current'],'page')
  assert.equal(s.find(p=>p.className==='button home-workspace-primary').props.href,'#request')
  assert.ok(s.find((p,n)=>n.type==='main'&&p.className==='home-workspace-main'))
  s.navigate('#help');await s.settle()
  assert.ok(s.find((p,n)=>n.type==='main'&&p.className==='home-workspace-main'))
  assert.equal(s.find(p=>p.href==='#help').props['aria-current'],'page')
  s.navigate('#enroll');await s.settle()
  assert.deepEqual(calls,['/me'])
  assert.equal(s.find(p=>p.href==='#team'),undefined)
})

test('operations and helper navigation stays permission-scoped while the public landing keeps its original header',async()=>{
  const operator=await app(async()=>({owner:true,operator:true,helper:false}),false,{route:'#team'})
  assert.equal(operator.find(p=>p.href==='#team').props['aria-current'],'page')
  assert.equal(operator.find(p=>p.href==='#availability'),undefined)
  const helper=await app(async()=>({owner:false,operator:false,helper:true}),false,{route:'#availability'})
  assert.equal(helper.find(p=>p.href==='#availability').props['aria-current'],'page')
  assert.ok(helper.find(p=>p.href==='#payout'));assert.equal(helper.find(p=>p.href==='#team'),undefined)
  const publicHome=await app(async()=>assert.fail('Signed-out Home needs no private data'),false,{signedOut:true,route:'#home'})
  assert.ok(publicHome.find((p,n)=>n.type==='header'))
  assert.equal(publicHome.find((p,n)=>n.type==='aside'),undefined)
  assert.ok(publicHome.find(p=>p.href==='#how'))
})

test('server enrollment-only mode blocks every booking/helper deep link without mounting forms or calling their APIs',async()=>{
  const calls=[]
  const s=await app(async path=>{calls.push(path);return {owner:false,operator:false,helper:true,enrollmentOnly:true}},false,{route:'#request'})
  for(const route of ['#request','#visits','#visit/11111111-1111-4111-8111-111111111111','#availability','#payout','#helping']){
    s.navigate(route);await s.settle()
    assert.ok(s.find((p,n)=>typeof n.type==='function'&&n.type.name==='EnrollmentEntry'))
    assert.equal(s.find((p,n)=>['RequestVisit','Visit','SavedDetails'].includes(n.type)||n.type==='lazy-screen'),undefined)
  }
  assert.equal(s.find(p=>p.href==='#visits'),undefined)
  assert.equal(s.find(p=>p.href==='#request'),undefined)
  assert.equal(s.find(p=>p.href==='#payout'),undefined)
  assert.equal(s.find(p=>p.className==='button home-workspace-primary').props.href,'#enroll')
  assert.deepEqual(calls,['/me'])
})

test('enrollment-only staff retain their service desk while the server flag preserves full private staging when false',async()=>{
  const owner=await app(async()=>({owner:true,operator:true,enrollmentOnly:true}),false,{route:'#team'})
  assert.ok(owner.find((p,n)=>n.type==='lazy-screen'&&p.profile?.owner===true))
  assert.ok(owner.find(p=>p.href==='#team'))
  assert.equal(owner.find(p=>p.href==='#request'),undefined)
  const staging=await app(async()=>({owner:false,operator:false,enrollmentOnly:false}),false,{route:'#request',enrollmentBuild:true})
  assert.ok(staging.find((p,n)=>n.type==='RequestVisit'))
})

test('public enrollment build gives landing and account entry enrollment copy without exposing booking navigation',async()=>{
  const s=await app(async()=>assert.fail('Signed-out public landing has no private fetch'),false,
    {signedOut:true,enrollmentBuild:true,route:'#home'})
  assert.equal(s.find((p,n)=>typeof n.type==='function'&&n.type.name==='Home').props.enrollmentOnly,true)
  assert.equal(s.find(p=>p.href==='#visits'),undefined)
  assert.equal(s.find(p=>p.href==='#helping'),undefined)
  s.navigate('#sign-in?next=request')
  const account=s.find((p,n)=>n.type==='Account')
  assert.equal(account.props.next,'enroll');assert.equal(account.props.enrollmentOnly,true)
})


test('compact workspace menu toggles and closes on navigation without fetching another account',async()=>{
  const calls=[];
  const s=await app(async path=>{calls.push(path);return {owner:false,operator:false,helper:false}});
  const toggle=()=>s.find(p=>p['aria-controls']==='home-workspace-links');
  assert.equal(toggle().props['aria-expanded'],false);
  toggle().props.onClick();s.render();
  assert.equal(toggle().props['aria-expanded'],true);
  assert.match(s.find(p=>p.id==='home-workspace-links').props.className,/is-open/);
  s.navigate('#enroll');s.render();
  assert.equal(toggle().props['aria-expanded'],false);
  assert.deepEqual(calls,['/me']);
});

test('production Help links to one public overview and keeps CookCredit.com distinct',async()=>{
  const s=await app(async()=>assert.fail('Public Help needs no private fetch'),false,
    {signedOut:true,route:'#help',production:true})
  assert.equal(s.find(p=>p['aria-label']==='CookCredit Home').props.href,'https://cookcredit.com/home/')
  assert.equal(s.find(p=>p.children==='Home services').props.href,'https://cookcredit.com/home/')
  assert.equal(s.find(p=>p.children==='CookCredit.com').props.href,'https://cookcredit.com/')
  assert.equal(s.find(p=>p.children==='How it works').props.href,'https://cookcredit.com/home/#how')
  assert.equal(s.find(p=>p.href==='#home'),undefined)
  s.navigate('#home')
  assert.deepEqual(s.replacements,['https://cookcredit.com/home/'])
})
