import test from 'node:test'
import assert from 'node:assert/strict'
import {readFile} from 'node:fs/promises'
import vm from 'node:vm'
import {transformWithEsbuild} from 'vite'
import * as homeNavigation from '../home/navigation.js'
const {safeHomeRoute}=homeNavigation
import * as visitPresentation from '../home/visitPresentation.js'
import * as serviceAddress from '../home/serviceAddress.js'
import * as customerWorklist from '../home/customerWorklist.js'

// Actual screen handlers under controlled failures; browser acceptance is separate.
async function screen(name,api,owner=true,clipboard=async()=>{},props={},exportName='default',runtime={}) {
  const states=[],effects=[];let index,tree,queued
  const react={lazy:()=> 'lazy-screen',Suspense:'suspense',useState(initial){const slot=index++;if(!(slot in states))states[slot]=initial;
    return [states[slot],value=>{states[slot]=typeof value==='function'?value(states[slot]):value}]},
    useRef(initial){const slot=index++;return states[slot]||=( {current:initial} )},
    useEffect(fn,deps){const slot=index++,old=effects[slot];if(!old||deps.some((d,i)=>d!==old.deps[i]))
      queued.push(()=>{old?.cleanup?.();effects[slot]={deps,cleanup:fn()}})},Fragment:'fragment'}
  const jsx=(type,props,key)=>({type,props,key})
  const modules={react,'react/jsx-runtime':{jsx,jsxs:jsx,Fragment:'fragment'},
    '../api':{api,label:v=>v,money:v=>String(v),dollars:Number},
    './api':{api,label:v=>v,money:v=>String(v),dollars:Number},
    '../src/firebase':{auth:{},getAppCheckHeaders:async()=>({})},
    './navigation':homeNavigation,
    '../../api':{api,label:v=>v,money:v=>String(v),dollars:Number},
    './Enrollment':{serviceNames:{both:'Cooking and cleaning',cooking:'Cooking',cleaning:'Cleaning',not_sure:'Help choosing'}},
    './OperatingRulesDraft':{__esModule:true,default:()=>null},
    './Availability':{__esModule:true,default:()=>null},
    './CustomerWorklist':{__esModule:true,default:function CustomerWorklist(){}},
    '../customerWorklist':customerWorklist,
    './customerWorklist':customerWorklist,
    './SavedDetails':{__esModule:true,default:function SavedDetails(){}},
    '../customerWorklist.css':{},
    './SuggestedTimes':{__esModule:true,default:()=>null},
    '../HomeErrorBoundary':{__esModule:true,default:'home-boundary'},
    '../visitPresentation':visitPresentation,
    '../serviceAddress':serviceAddress,
    './visitPresentation':visitPresentation,
    '../../src/utils/errorReporting':{reportClientError(){}}}
  Object.assign(modules,runtime.modules)
  modules['./screens/Enrollment'] ||= modules['./Enrollment']
  let source=await readFile(new URL(`../home/screens/${name}.jsx`,import.meta.url),'utf8')
  if(exportName!=='default')source+='\nexport { '+exportName+' };'
  const {code}=await transformWithEsbuild(source,name+'.jsx',{loader:'jsx',jsx:'automatic',format:'cjs'})
  const context={module:{exports:{}},require:id=>modules[id],URL,URLSearchParams,crypto,window:{scrollTo(){}},
    location:{href:'https://home.example.test/#team',origin:'https://home.example.test'},navigator:{clipboard:{writeText:clipboard}},
    FormData:class {constructor(values){this.values=values}has(key){return this.values[key]===true}get(key){return this.values[key]??null}
      getAll(key){return Array.isArray(this.values[key])?this.values[key]:[]}},...runtime.context}
  vm.runInNewContext(code,context)
  const Component=context.module.exports[exportName]
  function render(){index=0;queued=[];tree=Component({profile:{owner,email:'member@example.test'},...props});queued.forEach(fn=>fn())}
  function nodes(node){if(node==null||node===false)return [];if(Array.isArray(node))return node.flatMap(nodes);
    return [node,...nodes(node.props?.children)]}
  const text=()=>nodes(tree).filter(n=>typeof n==='string'||typeof n==='number').join(' ')
  const find=predicate=>nodes(tree).find(n=>n?.props&&predicate(n.props,n))
  async function settle(){await new Promise(resolve=>setImmediate(resolve));render()}
  render();return {render,settle,text,find,location:context.location,
    unmount(){effects.forEach(effect=>effect?.cleanup?.())}}
}

test('enrollment load errors retry instead of displaying empty or successful enrollment',async()=>{
  let fail=true
  const s=await screen('Enrollment',async()=>{if(fail)throw new Error('Connection lost');return {enrollment:null}})
  await s.settle();assert.match(s.text(),/Connection lost/)
  assert.equal(s.find((p,n)=>n.type==='form'),undefined)
  fail=false;s.find(p=>p.children==='Try again').props.onClick();s.render();await s.settle()
  assert.ok(s.find((p,n)=>n.type==='form'))
})

test('Google account recovery opens the chooser in the click and returns to the callback instead of another dashboard',async()=>{
  const events=[];let provider
  class GoogleAuthProvider { setCustomParameters(value){this.parameters=value} }
  const s=await screen('Account',async()=>assert.fail('Popup click must not need an extra API'),false,async()=>{},
    {user:null,next:'callback',refresh:async()=>{events.push('refresh')}},'default',{
      modules:{'firebase/auth':{GoogleAuthProvider,signInWithPopup(_auth,value){provider=value;events.push('popup');return Promise.resolve()}},
        '../../src/firebase':{auth:{}},'../../src/utils/verifyAccountLink':{},
        '../navigation':{safeHomeRoute,readReturnRoute:()=>null,rememberReturnRoute(){},forgetReturnRoute(){events.push('forget')}}},
      context:{location:{hash:'#sign-in?next=callback'}},
    })
  s.find(p=>p.className==='google').props.onClick()
  assert.deepEqual(events,['popup'])
  assert.equal(JSON.stringify(provider.parameters),JSON.stringify({prompt:'select_account'}))
  await s.settle()
  assert.equal(s.location.hash,'callback')
  assert.deepEqual(events,['popup','refresh','forget'])
})

test('public account sign-in maps an old booking destination to enrollment without collecting service details',async()=>{
  class GoogleAuthProvider { setCustomParameters(){} }
  const s=await screen('Account',async()=>assert.fail('Account entry must not call booking APIs'),false,async()=>{},
    {user:null,next:'request',enrollmentOnly:true,refresh:async()=>{}},'default',{
      modules:{'firebase/auth':{GoogleAuthProvider,signInWithPopup:async()=>{}},'../../src/firebase':{auth:{}},
        '../../src/utils/verifyAccountLink':{},'../navigation':{safeHomeRoute,readReturnRoute:()=> 'visits',rememberReturnRoute(){},forgetReturnRoute(){}}},
      context:{location:{hash:'#sign-in?next=request'}},
    })
  assert.match(s.text(),/Enrollment does not book a visit or take payment/)
  assert.doesNotMatch(s.text(),/Your Home visits/)
  assert.equal(s.find(p=>p.name==='address'),undefined)
  s.find(p=>p.className==='google').props.onClick();await s.settle()
  assert.equal(s.location.hash,'enroll')
})

test('known private Home denial offers account recovery and contact without another doomed callback submission',async()=>{
  let switched=0
  const s=await screen('../App',async()=>assert.fail('Blocked callback must not submit'),false,async()=>{},
    {user:{email:'fixture@example.test',emailVerified:true},accessErrorCode:'private_acceptance',
      returnTo:'callback',switchAccount:()=>{switched++}},'Help')
  assert.equal(s.find((p,n)=>n.type==='form'),undefined)
  assert.match(s.text(),/sign-in worked/);assert.match(s.text(),/No callback request was submitted/)
  assert.match(s.text(),/fixture@example.test/)
  assert.ok(s.find(p=>p.href==='mailto:connectwithus@cookcredit.com'))
  s.find(p=>p.children==='Use a different account').props.onClick();assert.equal(switched,1)
})

test('private Help waits for identity and requires sign-in before collecting callback contact details',async()=>{
  const api=async()=>assert.fail('Private signed-out Help must not submit or discover metadata')
  const loading=await screen('../App',api,false,async()=>{},{privateAcceptance:true,returnTo:'help'},'Help')
  assert.match(loading.text(),/Checking your account/)
  assert.equal(loading.find((p,n)=>n.type==='form'),undefined)
  const signedOut=await screen('../App',api,false,async()=>{},{user:null,privateAcceptance:true,returnTo:'help'},'Help')
  assert.match(signedOut.text(),/Sign in before sending/)
  assert.equal(signedOut.find(p=>p.name==='phone'),undefined)
  assert.ok(signedOut.find(p=>p.href==='#sign-in?next=help'))
  const unverified=await screen('../App',api,false,async()=>{},
    {user:{email:'fixture@example.test',emailVerified:false},privateAcceptance:true,returnTo:'callback'},'Help')
  assert.equal(unverified.find((p,n)=>n.type==='form'),undefined)
  assert.ok(unverified.find(p=>p.href==='#sign-in?next=callback'))
})

test('anonymous public callbacks stay available while an actual authentication rejection offers a return to Help',async()=>{
  let calls=0
  const s=await screen('../App',async()=>{calls++;throw Object.assign(new Error('Missing authorization'),{status:401})},
    false,async()=>{},{user:null,returnTo:'callback'},'Help')
  const form=s.find((p,n)=>n.type==='form');assert.ok(form)
  await form.props.onSubmit({preventDefault(){},currentTarget:{name:'Example',phone:'4045550123',time:'Afternoon',consent:'on'}})
  s.render()
  assert.match(s.text(),/Sign in before sending/);assert.doesNotMatch(s.text(),/callback request is received/)
  assert.ok(s.find(p=>p.href==='#sign-in?next=callback'))
  assert.equal(s.find((p,n)=>n.type==='form'),undefined)
  s.render();assert.equal(calls,1)
})

test('enrollment-only public Help accepts only an explicitly consented call request with staff-purpose disclosure',async()=>{
  const calls=[]
  const s=await screen('../App',async(...args)=>{calls.push(args);return {received:true}},false,async()=>{},
    {user:null,enrollmentOnly:true,returnTo:'callback'},'Help')
  assert.match(s.text(),/authorized CookCredit Home staff/)
  assert.match(s.text(),/not advertising/)
  assert.ok(s.find(p=>p.href==='https://cookcredit.com/privacy.html'))
  assert.equal(s.find(p=>p.name==='address'),undefined)
  await s.find((p,n)=>n.type==='form').props.onSubmit({preventDefault(){},currentTarget:{name:'Synthetic',phone:'4045550123',time:'Afternoon',consent:'on'}})
  s.render()
  assert.match(s.text(),/callback request is received/)
  assert.equal(calls.length,1);assert.equal(calls[0][0],'/callbacks')
  assert.equal(calls[0][1].body.contactConsent,true)
  assert.equal('address' in calls[0][1].body,false)
})

test('enabled staging customers may submit and a second callback is only created after an explicit new request',async()=>{
  const calls=[]
  const s=await screen('../App',async(path,options)=>{calls.push([path,options]);return {received:true}},false,async()=>{},
    {user:{emailVerified:true},profile:{environment:'staging'},returnTo:'help'},'Help')
  const event={preventDefault(){},currentTarget:{name:'Example',phone:'4045550123',time:'Afternoon',consent:'on'}}
  await s.find((p,n)=>n.type==='form').props.onSubmit(event);s.render()
  assert.match(s.text(),/callback request is received/);assert.match(s.text(),/visit has not been booked/)
  assert.equal(s.find(p=>p.children==='Back to my visits').props.href,'#visits')
  s.find(p=>p.children==='Request another call').props.onClick();s.render()
  assert.equal(calls.length,1);assert.ok(s.find((p,n)=>n.type==='form'))
  await s.find((p,n)=>n.type==='form').props.onSubmit(event);s.render()
  assert.equal(calls.length,2);assert.notEqual(calls[0][1].body.requestId,calls[1][1].body.requestId)
})

test('My visits retries its failed read only on request and restores the scoped list',async()=>{
  const calls=[];let finish
  const s=await screen('../App',async path=>{
    calls.push(path)
    if(calls.length===1)throw new Error('Visits temporarily unavailable')
    return new Promise(resolve=>{finish=resolve})
  },false,async()=>{},{},'Visits')
  await s.settle();assert.ok(s.find(p=>p.error==='Visits temporarily unavailable'))
  assert.doesNotMatch(s.text(),/No visits yet/)
  assert.deepEqual(calls,['/visits'])
  const retry=s.find(p=>p.children==='Refresh visits')
  assert.ok(retry)
  const pending=retry.props.onClick();s.render()
  assert.match(s.text(),/Loading visits/)
  assert.equal(s.find(p=>p.children==='Refresh visits'),undefined)
  assert.deepEqual(calls,['/visits','/visits'])
  finish({visits:[{id:'own-visit',service:'cooking',date:'2030-01-07',time:'10:00',durationMinutes:120,status:'requested'}],nextCursor:null})
  await pending;s.render()
  assert.ok(s.find(p=>p.href==='#visit/own-visit'))
  assert.doesNotMatch(s.text(),/Visits temporarily unavailable/)
  assert.equal(calls.length,2)
})

test('customer visit rows reuse readable service schedules and statuses without extra requests or raw record identifiers',async()=>{
  const calls=[]
  const rows=[{id:'private-visit-id',service:'both',date:'2026-11-07',time:'13:30:00',timeZone:'America/New_York',durationMinutes:150,status:'pending_confirmation'},
    {id:'another-private-id',service:'new_service',date:null,time:null,timeZone:null,durationMinutes:60,status:'future_state'}]
  const s=await screen('../App',async path=>{calls.push(path);return {visits:rows,nextCursor:null}},false,async()=>{},{},'Visits')
  await s.settle()
  assert.deepEqual(calls,['/visits'])
  assert.match(s.text(),/Cooking and cleaning/)
  assert.match(s.text(),/Saturday, November 7, 2026/)
  assert.match(s.text(),/1:30 PM/);assert.match(s.text(),/Eastern time/)
  assert.match(s.text(),/Ready for your review/)
  assert.match(s.text(),/Date to be reviewed/);assert.match(s.text(),/Time to be reviewed/)
  assert.match(s.text(),/Home visit/);assert.match(s.text(),/Visit update/)
  assert.doesNotMatch(s.text(),/private-visit-id|another-private-id|pending_confirmation|future_state|new_service|2026-11-07|13:30:00|Invalid Date/)
  assert.ok(s.find(p=>p.href==='#visit/private-visit-id'))
})

test('owner visit list uses the same schedule and status labels after an explicit tab change',async()=>{
  const calls=[]
  const s=await screen('Team',async path=>{
    calls.push(path)
    return path==='/enrollments'?{enrollments:[]}:{visits:[{id:'private-team-visit',service:'both',date:'2026-11-07',time:'13:30:00',
      timeZone:'America/New_York',durationMinutes:150,status:'pending_confirmation'}],nextCursor:null}
  })
  await s.settle()
  s.find(p=>p.children==='Visits').props.onClick();s.render();await s.settle()
  assert.deepEqual(calls,['/visits'])
  assert.match(s.text(),/Cooking and cleaning/)
  assert.match(s.text(),/Saturday, November 7, 2026/)
  assert.match(s.text(),/1:30 PM/);assert.match(s.text(),/Eastern time/)
  assert.match(s.text(),/Ready for your review/)
  assert.doesNotMatch(s.text(),/private-team-visit|pending_confirmation|2026-11-07|13:30:00/)
  assert.ok(s.find(p=>p.href==='#visit/private-team-visit'))
})

test('an acknowledged visit does not redirect or save household details after leaving the request screen',async()=>{
  const calls=[];let acknowledge
  const s=await screen('RequestVisit',async(path,options)=>{
    calls.push([path,options])
    if(path==='/household')return {household:null}
    return new Promise(resolve=>{acknowledge=resolve})
  },false)
  await s.settle()
  const event={preventDefault(){},currentTarget:{}}
  await s.find((p,n)=>n.type==='form').props.onSubmit(event);s.render()
  await s.find((p,n)=>n.type==='form').props.onSubmit(event);s.render()
  const pending=s.find((p,n)=>n.type==='form').props.onSubmit({preventDefault(){},currentTarget:{
    cooking:'120',date:'2030-01-07',time:'10:00',street:'100 Example Street',unit:'Unit 2',city:'Atlanta',state:'GA',postalCode:'30315',repeatPreference:'once',notes:'',consent:'on',remember:'on',
  }})
  s.unmount();s.location.hash='home'
  acknowledge({id:'saved-visit'});await pending
  assert.equal(s.location.hash,'home')
  assert.deepEqual(calls.map(([path,options])=>[path,options?.method]),[['/household',undefined],['/visits','POST']])
})

test('leaving during an explicitly requested household save does not pull the customer back to the visit',async()=>{
  const calls=[];let finishSave
  const s=await screen('RequestVisit',async(path,options)=>{
    calls.push([path,options])
    if(path==='/visits')return {id:'saved-visit'}
    if(options)return new Promise(resolve=>{finishSave=resolve})
    return {household:null}
  },false)
  await s.settle()
  const event={preventDefault(){},currentTarget:{}}
  await s.find((p,n)=>n.type==='form').props.onSubmit(event);s.render()
  await s.find((p,n)=>n.type==='form').props.onSubmit(event);s.render()
  const pending=s.find((p,n)=>n.type==='form').props.onSubmit({preventDefault(){},currentTarget:{
    cooking:'120',date:'2030-01-07',time:'10:00',street:'100 Example Street',unit:'Unit 2',city:'Atlanta',state:'GA',postalCode:'30315',repeatPreference:'once',notes:'',consent:'on',remember:'on',
  }})
  await new Promise(resolve=>setImmediate(resolve))
  assert.equal(calls.at(-1)[1].method,'PUT')
  s.unmount();s.location.hash='home';finishSave({saved:true});await pending
  assert.equal(s.location.hash,'home')
  assert.equal(calls.filter(([path])=>path==='/visits').length,1)
})

test('enrollment save uses the existing account endpoint and only claims success after acknowledgement',async()=>{
  const calls=[];let fail=true
  const s=await screen('Enrollment',async(path,options)=>{calls.push([path,options]);
    if(!options)return {enrollment:null};if(fail)throw new Error('Retry safely');return {enrollment:{service:'both'}}})
  await s.settle()
  s.find(p=>p.value==='both').props.onChange();s.render()
  assert.ok(s.find(p=>p.autoComplete==='name').props.required)
  s.find(p=>p.autoComplete==='name').props.onChange({target:{value:'Jordan Smith'}});s.render()
  const submit=()=>s.find((p,n)=>n.type==='form').props.onSubmit({preventDefault(){},currentTarget:{contactConsent:true}})
  await submit();s.render();assert.match(s.text(),/Retry safely/);assert.doesNotMatch(s.text(),/Your preferences are saved/)
  fail=false;await submit();s.render();assert.match(s.text(),/Your preferences are saved/)
  assert.equal(calls.length,3)
  assert.equal(calls[2][0],'/enrollment');assert.equal(calls[2][1].method,'PUT')
  assert.equal(JSON.stringify(calls[2][1].body),JSON.stringify({service:'both',phone:'',name:'Jordan Smith',contactConsent:true}))
})

test('a returning enrolled customer sees saved needs and can explicitly edit without another enrollment request',async()=>{
  const calls=[]
  const s=await screen('Enrollment',async(path,options)=>{
    calls.push([path,options]);return {enrollment:{service:'both',phone:'',status:'active'}}
  },false,async()=>{},{profile:{email:'fixture@example.test',enrollmentOnly:true}})
  await s.settle()
  assert.match(s.text(),/You’re on the list/)
  assert.match(s.text().replace(/\s+/g,' '),/cooking and cleaning is saved/)
  assert.equal(s.find((p,n)=>n.type==='form'),undefined)
  s.find(p=>p.children==='Edit my needs').props.onClick();s.render()
  assert.ok(s.find(p=>p.value==='both').props.checked)
  assert.ok(s.find(p=>p.name==='contactConsent').props.required)
  assert.equal(s.find(p=>p.name==='contactConsent').props.checked,undefined)
  assert.deepEqual(calls,[['/enrollment',undefined]])
})

test('only the owner mounts the customer worklist without a second legacy directory request',async()=>{
  const calls=[]
  const api=async path=>{calls.push(path);return path==='/enrollments'?{enrollments:[]}:{visits:[]}}
  const operator=await screen('Team',api,false);await operator.settle()
  assert.deepEqual(calls,['/visits']);assert.doesNotMatch(operator.text(),/People enrolled/)
  const worklist=s=>s.find((p,n)=>n.type?.name==='CustomerWorklist')
  assert.equal(worklist(operator),undefined)
  const owner=await screen('Team',api,true);await owner.settle()
  assert.deepEqual(calls,['/visits'])
  assert.ok(worklist(owner));assert.doesNotMatch(owner.text(),/Loading/)
})

test('clicking the selected service-desk tab keeps its loaded data and does not strand the page on Loading',async()=>{
  const calls=[]
  const s=await screen('Team',async path=>{calls.push(path);return {enrollments:[]}})
  await s.settle();assert.ok(s.find((p,n)=>n.type?.name==='CustomerWorklist'))
  s.find((p,n)=>n.type==='button'&&p.children==='Customers').props.onClick();s.render();await s.settle()
  assert.ok(s.find((p,n)=>n.type?.name==='CustomerWorklist'));assert.doesNotMatch(s.text(),/Loading/)
  assert.deepEqual(calls,[])
})

test('service desk groups settings behind disclosure and loads only the explicitly selected section',async()=>{
  const calls=[]
  const s=await screen('Team',async(path,options)=>{calls.push([path,options]);
    return path==='/enrollments'?{enrollments:[]}:{activeId:null,versions:[]}})
  await s.settle()
  assert.ok(s.find(p=>p.children==='Customers'));assert.match(s.text(),/Daily work/)
  const settings=()=>s.find((p,n)=>n.type==='details'&&p.className==='home-desk-group home-desk-settings')
  assert.equal(settings().props.open,false)
  assert.ok(s.find((p,n)=>n.type?.name==='CustomerWorklist'))
  assert.deepEqual(calls,[])
  s.find(p=>p.children==='Pricing').props.onClick();s.render();await s.settle()
  assert.equal(settings().props.open,true)
  assert.deepEqual(calls.map(([path])=>path),['/pricing'])
  assert.ok(calls.every(([,options])=>!options))
  assert.equal(s.find(p=>p.children==='Refresh people'),undefined)
})

test('public enrollment desk exposes owner setup without opening customer booking',async()=>{
  const calls=[]
  const owner=await screen('Team',async path=>{calls.push(path);return path==='/enrollments'?{enrollments:[]}:{events:[]}},true,async()=>{},
    {profile:{owner:true,operator:true,enrollmentOnly:true}})
  await owner.settle()
  assert.doesNotMatch(owner.text(),/Helpers|Hours and scheduling/)
  assert.ok(owner.find((p,n)=>n.type==='button'&&p.children==='Pricing'))
  assert.ok(owner.find((p,n)=>n.type==='button'&&p.children==='Payment operations'))
  assert.equal(owner.find((p,n)=>n.type==='button'&&p.children==='Callbacks'),undefined)
  assert.ok(owner.find((p,n)=>n.type?.name==='CustomerWorklist'))
  assert.equal(owner.find((p,n)=>n.type==='button'&&p.children==='Visits'),undefined)
  owner.find((p,n)=>n.type==='button'&&p.children==='Activity log').props.onClick();owner.render();await owner.settle()
  assert.deepEqual(calls,['/audit'])
  const operatorCalls=[]
  const operator=await screen('Team',async path=>{operatorCalls.push(path);return {callbacks:[]}},false,async()=>{},
    {profile:{owner:false,operator:true,enrollmentOnly:true}})
  await operator.settle()
  assert.deepEqual(operatorCalls,['/callbacks'])
  assert.equal(operator.find((p,n)=>n.type==='button'&&p.children==='Customers'),undefined)
  assert.equal(operator.find((p,n)=>n.type==='button'&&p.children==='Activity log'),undefined)
})

test('public enrollment saves interest only and offers a call with clear information and withdrawal controls',async()=>{
  const calls=[]
  const s=await screen('Enrollment',async(path,options)=>{calls.push([path,options]);return options?{saved:true}:{enrollment:null}},false,async()=>{},
    {profile:{email:'fixture@example.test',enrollmentOnly:true}})
  await s.settle()
  assert.match(s.text(),/not advertising consent/)
  assert.ok(s.find(p=>p.href==='https://cookcredit.com/privacy.html'))
  assert.equal(s.find(p=>p.name==='address'),undefined)
  s.find(p=>p.value==='cooking').props.onChange();s.render()
  await s.find((p,n)=>n.type==='form').props.onSubmit({preventDefault(){},currentTarget:{contactConsent:true}});s.render()
  assert.equal(s.find(p=>p.href==='#request'),undefined)
  assert.ok(s.find(p=>p.href==='#callback'))
  assert.ok(s.find(p=>p.children==='Remove my service needs'))
  assert.equal(calls.length,2);assert.equal(calls[1][0],'/enrollment');assert.equal(calls[1][1].method,'PUT')
  assert.equal(JSON.stringify(calls[1][1].body),JSON.stringify({service:'cooking',phone:'',name:'',contactConsent:true}))
})

test('enrollment-only landing, explanation and blocked entry never offer booking or health intake',async()=>{
  for(const name of ['Home','How','EnrollmentEntry']){
    const s=await screen('../App',async()=>assert.fail('Public copy requires no API'),false,async()=>{},{enrollmentOnly:true},name)
    assert.ok(s.find(p=>p.href==='#enroll'))
    assert.equal(s.find(p=>p.href==='#request'),undefined)
    assert.equal(s.find((p,n)=>n.type==='form'),undefined)
    assert.doesNotMatch(s.text(),/Arrange a visit|Pay securely|Share food allergies/)
    assert.match(s.text(),/not available/)
  }
})

test('operator assignment excludes the customer even if they are an approved helper',async()=>{
  const s=await screen('operator/OperatorVisit',async path=>path==='/helpers'?{helpers:[
    {id:'customer',name:'Customer cannot be their own helper',enabled:true,cooking:true,cleaning:true},
    {id:'other',name:'Eligible helper',enabled:true,cooking:true,cleaning:true},
  ]}:path==='/pricing'?{}:{events:[]},true,async()=>{},
    {visit:{id:'visit',version:1,status:'requested',reviewed:true,customerId:'customer',service:'cooking'},receipts:[]})
  await s.settle()
  assert.doesNotMatch(s.text(),/Customer cannot be their own helper/)
  assert.match(s.text(),/Eligible helper/)
})

test('arrange visit carries the saved enrollment choice without overriding later form edits',async()=>{
  let chosen
  const enrollment=await screen('Enrollment',async(path,options)=>options?{saved:true}:{enrollment:{service:'both'}},
    false,async()=>{},{onArrange:value=>{chosen=value}})
  await enrollment.settle()
  assert.match(enrollment.text(),/Your preferences are saved/)
  enrollment.find(p=>p.href==='#request').props.onClick()
  assert.equal(chosen,'both')
  const visit=await screen('RequestVisit',async()=>({household:null}),false,async()=>{},{initialService:chosen})
  await visit.settle()
  assert.equal(visit.find(p=>p.name==='cleaning').props.value,60)
  assert.ok(visit.find((p,n)=>n.type==='input'&&p.name==='service'&&p.checked))
  // The chosen service remains editable after entry; loading saved household
  // data must not reset the user's explicit selection.
  const cooking=visit.find((p,n)=>n.type==='label'&&Array.isArray(p.children)&&p.children.includes('Cooking'))
  cooking.props.children.find(n=>n?.type==='input').props.onChange()
  visit.render();await visit.settle()
  assert.equal(visit.find(p=>p.name==='cleaning'),undefined)
  const unsure=await screen('RequestVisit',async()=>({household:null}),false,async()=>{},{initialService:'not_sure'})
  await unsure.settle()
  assert.equal(unsure.find(p=>p.name==='cleaning'),undefined)
})

test('approved unpaid quotes show the payment step; expired quotes explain why checkout is unavailable',async()=>{
  const value={id:'visit',version:1,status:'accepted',service:'both',isCustomer:true,time:'10:00',
    instructions:{preferences:[],cleaningTasks:[]},payment:{status:'unpaid'},
    quote:{approved:true,helperAcceptedQuote:true,expired:false,labor:[],materials:[],expiresAt:'2030-01-01'}}
  const api=async path=>path.endsWith('/receipts')?{receipts:[]}:value
  const open=()=>screen('Visit',api,false,async()=>{},{id:'visit',profile:{paymentsAvailable:true}})
  const approved=await open();await approved.settle()
  assert.match(approved.text(),/full quote is approved\. Payment must be confirmed/)
  const payButton=(p,n)=>n.type==='button'&&typeof p.children==='string'&&p.children.startsWith('Pay up to')
  assert.ok(approved.find(payButton))
  value.quote.expired=true
  const expired=await open();await expired.settle()
  assert.match(expired.text(),/quote has expired/)
  assert.equal(expired.find(payButton),undefined)
})

test('an unknown provider transfer balance stays explicit and cannot be dismissed as an ordinary reviewed issue',async()=>{
  const value={id:'visit',version:2,status:'completed',service:'cooking',isCustomer:true,time:'10:00',issueOpen:true,
    instructions:{preferences:[],cleaningTasks:[]},payment:{status:'review_required',helperFunds:'provider_review_required',
      helperTransferBalanceKnown:false,helperTransferredCents:null},quote:null}
  const view=await screen('Visit',async path=>path.endsWith('/receipts')?{receipts:[]}:value,false,async()=>{},
    {id:'visit',profile:{paymentsAvailable:false}})
  await view.settle();assert.match(view.text(),/transfer balance needs review/)
  assert.doesNotMatch(view.text(),/funds have not been released/)
  const ops=await screen('operator/OperatorVisit',async path=>path==='/helpers'?{helpers:[]}:path==='/pricing'?{}:{events:[]},
    true,async()=>{},{visit:value,receipts:[]})
  await ops.settle();assert.match(ops.text(),/Reconcile the external transfer change/)
  assert.equal(ops.find(p=>p.children==='Resolve reviewed issue').props.disabled,true)
})

test('requested visit is a readable unconfirmed plan with shared preference labels and customer next steps',async()=>{
  const calls=[]
  const value={id:'visit',version:2,status:'requested',service:'cooking',isCustomer:true,
    date:'2026-11-07',time:'10:00:00',timeZone:'America/New_York',durationMinutes:120,address:'Synthetic address',
    instructions:{preferences:['allergies','phone_help','easy_to_chew'],cleaningTasks:[],visitNotes:'Example note'},
    payment:{status:'unpaid'},quote:null}
  const view=await screen('Visit',async(path,options)=>{calls.push([path,options]);return path.endsWith('/receipts')?{receipts:[]}:value},
    false,async()=>{},{id:'visit',profile:{paymentsAvailable:false}})
  await view.settle()
  assert.match(view.text(),/Request received/)
  assert.match(view.text(),/Saturday, November 7, 2026/)
  assert.match(view.text(),/10:00 AM\s+·\s+Eastern time/)
  assert.match(view.text(),/Requested date/)
  assert.match(view.text(),/Food allergies or ingredients to avoid/)
  assert.match(view.text(),/Discuss my request by phone first/)
  assert.match(view.text(),/Easy-to-chew meals/)
  assert.match(view.text(),/No payment due now/)
  assert.match(view.text(),/No receipts yet/)
  assert.doesNotMatch(view.text(),/helper fund release|JPEG|PNG|Time arranged/)
  assert.equal(calls.some(([,options])=>options?.method==='POST'),false)
  view.find(p=>p.children==='Report a problem').props.onClick();view.render()
  assert.equal(calls.some(([,options])=>options?.method==='POST'),false)
  assert.match(view.text(),/pauses visit progress/)
  view.find(p=>p.children==='Keep this visit unchanged').props.onClick();view.render()
  assert.equal(view.find(p=>p.children==='Send for review'),undefined)
  view.find(p=>p.children==='Report a problem').props.onClick();view.render()
  await view.find(p=>p.children==='Send for review').props.onClick();view.render()
  const writes=calls.filter(([,options])=>options?.method==='POST')
  assert.equal(writes.length,1)
  assert.equal(writes[0][0],'/visits/visit/actions')
  assert.equal(writes[0][1].body.action,'report_issue')
  assert.equal(writes[0][1].body.version,2)
})

test('an open visit issue stays visible and blocked while customer copy omits ordinary helper payout details',async()=>{
  const value={id:'visit',version:3,status:'requested',service:'cooking',isCustomer:true,issueOpen:true,time:'10:00',
    instructions:{preferences:[],cleaningTasks:[]},payment:{status:'unpaid'},quote:null}
  const api=async path=>path.endsWith('/receipts')?{receipts:[]}:value
  const customer=await screen('Visit',api,false,async()=>{},{id:'visit',profile:{paymentsAvailable:false}})
  await customer.settle()
  assert.match(customer.text(),/CookCredit review is needed/)
  assert.match(customer.text(),/An issue has been reported/)
  assert.equal(customer.find(p=>p.children==='Report a problem'),undefined)
  assert.doesNotMatch(customer.text(),/helper transfers remain on hold|helper fund release/)
  assert.ok(customer.find(p=>p.href==='#help'))
  const helper=await screen('Visit',api,false,async()=>{},{id:'visit',profile:{operator:true,paymentsAvailable:false}})
  await helper.settle()
  assert.match(helper.text(),/New helper transfers remain on hold/)
})

test('owner operating draft starts closed and saves versioned rules without an activation request',async()=>{
  const calls=[]
  const draft=await screen('OperatingRulesDraft',async(...args)=>{calls.push(args)},true,async()=>{},
    {data:{version:0,rules:{states:['GA'],timeZone:'America/New_York',noticeHours:24,shortNoticeHours:6,bufferMinutes:null,weeklyHours:[]}},run:task=>task()})
  assert.match(draft.text(),/All days are currently closed/)
  assert.match(draft.text(),/does not publish appointment slots/)
  assert.equal(draft.find(p=>p.name==='notice').props.defaultValue,24)
  await draft.find((p,n)=>n.type==='form').props.onSubmit({preventDefault(){},currentTarget:{
    states:' ga, GA ',zone:'America/New_York',notice:'24',short:'6',buffer:'',mon:true,'mon-start':'09:00','mon-end':'00:00',
  }})
  assert.equal(calls.length,1);assert.equal(calls[0][0],'/operating-rules')
  const body=calls[0][1].body
  assert.equal(body.version,0);assert.equal(body.rules.bufferMinutes,null)
  assert.equal(JSON.stringify(body.rules.weeklyHours),JSON.stringify([{day:'mon',startMinute:540,endMinute:1440}]))
  assert.equal('published' in body,false);assert.equal('enabled' in body,false)
})

test('helper schedule load failures retry and operator view cannot edit hours',async()=>{
  let fail=true;const calls=[]
  const s=await screen('Availability',async path=>{calls.push(path);if(fail)throw new Error('Temporary schedule outage');
    return {version:0,configured:false,timeZone:'America/New_York',weeklyHours:[],blockedDates:[]}},
    true,async()=>{},{helperId:'helper-with/slash'})
  await s.settle();assert.match(s.text(),/Temporary schedule outage/)
  fail=false;s.find(p=>p.children==='Refresh availability').props.onClick();s.render();await s.settle()
  assert.match(s.text(),/Only this helper can change/)
  assert.equal(s.find((p,n)=>n.type==='form'),undefined)
  assert.deepEqual(calls,['/helpers/helper-with%2Fslash/availability','/helpers/helper-with%2Fslash/availability'])
})

test('helper schedule form saves closed days and blocked dates through the versioned own-account API',async()=>{
  const saved=[];const data={version:3,timeZone:'America/New_York',weeklyHours:[],blockedDates:['2026-12-01']}
  const s=await screen('Availability',async()=>{},false,async()=>{},
    {data,save:async body=>saved.push(body),busy:false},'ScheduleForm')
  assert.match(s.text(),/no available work days/)
  assert.equal(s.find(p=>p.name==='mon-start').props.disabled,true)
  s.find(p=>Array.isArray(p.children)&&p.children.join('')==='Remove 2026-12-01').props.onClick();s.render()
  await s.find((p,n)=>n.type==='form').props.onSubmit({preventDefault(){},currentTarget:{mon:true,'mon-start':'9','mon-end':'24'}})
  assert.equal(JSON.stringify(saved[0]),JSON.stringify({version:3,timeZone:'America/New_York',blockedDates:[],
    weeklyHours:[{day:'mon',startHour:9,endHour:24}]}))
})

test('failed helper schedule save keeps the editable form and does not claim success',async()=>{
  const calls=[];const data={version:2,configured:true,timeZone:'America/New_York',weeklyHours:[],blockedDates:[]}
  const s=await screen('Availability',async(path,options)=>{calls.push([path,options]);if(options)throw new Error('Existing visit conflicts');return data})
  await s.settle()
  const form=s.find((p,n)=>typeof n.type==='function'&&n.type.name==='ScheduleForm')
  await form.props.save({version:2,timeZone:'America/New_York',weeklyHours:[],blockedDates:[]});s.render()
  assert.match(s.text(),/Existing visit conflicts/);assert.doesNotMatch(s.text(),/Availability saved/)
  assert.equal(calls[1][0],'/availability');assert.equal(calls[1][1].method,'PUT')
  assert.ok(s.find((p,n)=>typeof n.type==='function'&&n.type.name==='ScheduleForm'))
})

test('policy activation requires reviewed saved settings and never activates unsaved edits automatically',async()=>{
  const calls=[],notices=[]
  const data={version:2,rules:{states:['GA'],timeZone:'America/New_York',noticeHours:24,shortNoticeHours:6,
    bufferMinutes:60,weeklyHours:[{day:'mon',startMinute:600,endMinute:1080}]},activePolicy:null}
  const s=await screen('OperatingRulesDraft',async(...args)=>{calls.push(args)},true,async()=>{},
    {data,run:(task,message)=>{notices.push(message);return task()}})
  const button=()=>s.find(p=>p.children==='Activate saved rules')
  const acknowledgement=()=>s.find(p=>p.type==='checkbox'&&!p.name)
  assert.equal(calls.length,0);assert.equal(button().props.disabled,true)
  acknowledgement().props.onChange({target:{checked:true}});s.render();assert.equal(button().props.disabled,false)
  s.find((p,n)=>n.type==='form').props.onChange();s.render()
  assert.equal(button().props.disabled,true);assert.match(s.text(),/Save your changes before activating/)
  // A fresh acknowledged saved revision can be applied explicitly.
  const saved=await screen('OperatingRulesDraft',async(...args)=>{calls.push(args)},true,async()=>{},
    {data,run:(task,message)=>{notices.push(message);return task()}})
  saved.find(p=>p.type==='checkbox'&&!p.name).props.onChange({target:{checked:true}});saved.render()
  await saved.find(p=>p.children==='Activate saved rules').props.onClick()
  assert.equal(calls.length,1);assert.equal(calls[0][0],'/operating-rules/activate')
  assert.equal(JSON.stringify(calls[0][1].body),JSON.stringify({version:2,reviewConfirmed:true}))
  assert.match(notices[0],/still require review/)
  assert.match(saved.text(),/not reserved or automatically confirmed/)
})

test('incomplete and already active operating drafts cannot be reactivated through the owner controls',async()=>{
  const rules={states:['GA'],timeZone:'America/New_York',noticeHours:24,shortNoticeHours:6,bufferMinutes:null,weeklyHours:[]}
  const incomplete=await screen('OperatingRulesDraft',async()=>assert.fail('unexpected activation'),true,async()=>{},
    {data:{version:1,rules,activePolicy:null},run:task=>task()})
  assert.equal(incomplete.find(p=>p.children==='Activate saved rules').props.disabled,true)
  const complete={...rules,bufferMinutes:60,weeklyHours:[{day:'mon',startMinute:600,endMinute:1080}]}
  const active=await screen('OperatingRulesDraft',async()=>assert.fail('unexpected activation'),true,async()=>{},
    {data:{version:2,rules:complete,activePolicy:{version:2,rules:complete}},run:task=>task()})
  assert.match(active.text(),/saved draft is active/)
  assert.equal(active.find(p=>p.children==='Activate saved rules').props.disabled,true)
})

test('owner can reload a changed policy after a failed mutation without replaying the mutation',async()=>{
  const calls=[];const rules={states:['GA'],timeZone:'America/New_York',noticeHours:24,shortNoticeHours:6,bufferMinutes:60,weeklyHours:[]}
  const s=await screen('Team',async path=>{calls.push(path);return path==='/enrollments'?{enrollments:[]}:{version:2,rules,activePolicy:null}})
  await s.settle();s.find(p=>p.children==='Hours and scheduling').props.onClick();s.render();await s.settle()
  let editor=s.find(p=>typeof p.reload==='function'&&p.data?.rules)
  await editor.props.run(async()=>{throw new Error('Rules changed in another window')});s.render()
  assert.match(s.text(),/Rules changed in another window/)
  editor=s.find(p=>typeof p.reload==='function'&&p.data?.rules);editor.props.reload();s.render();await s.settle()
  assert.doesNotMatch(s.text(),/Rules changed in another window/)
  assert.deepEqual(calls,['/operating-rules','/operating-rules'])
})

const suggestions=(date='2026-12-01')=>({date,timeZone:'America/New_York',policyVersion:2,
  slots:[{time:'10:00',durationMinutes:120}],reviewRequired:true,reservesTime:false,areaReviewRequired:true})

test('time suggestions load only on explicit request and choosing one never creates a visit',async()=>{
  const calls=[],chosen=[],zones=[]
  const s=await screen('SuggestedTimes',async(...args)=>{calls.push(args);return suggestions()},false,async()=>{},
    {date:'2026-12-01',service:'cooking',durationMinutes:120,state:'GA',timeZone:'America/New_York',onChoose:t=>chosen.push(t),onTimeZone:z=>zones.push(z)})
  await s.settle();assert.equal(calls.length,0)
  await s.find(p=>p.children==='Check suggested times').props.onClick();s.render()
  assert.equal(calls.length,1);assert.match(calls[0][0],/^\/slots\?date=2026-12-01&durationMinutes=120&service=cooking&state=GA$/)
  assert.equal(calls[0][1],undefined)
  s.find(p=>p.children==='10:00 AM').props.onClick();s.render()
  assert.deepEqual(chosen,['10:00']);assert.deepEqual(zones,['America/New_York']);assert.equal(calls.length,1)
  assert.match(s.text(),/does not book a visit or charge/)
})

test('late slot responses cannot overwrite a changed date and failed checks remain retryable',async()=>{
  let resolveFirst;const calls=[]
  const props={date:'2026-12-01',service:'cooking',durationMinutes:120,timeZone:'America/New_York',onChoose(){}}
  const s=await screen('SuggestedTimes',async path=>{calls.push(path);if(calls.length===1)return new Promise(resolve=>{resolveFirst=resolve});
    return suggestions('2026-12-02')},false,async()=>{},props)
  const first=s.find(p=>p.children==='Check suggested times').props.onClick();s.render()
  props.date='2026-12-02';s.render();resolveFirst(suggestions());await first;s.render()
  assert.doesNotMatch(s.text(),/10:00 AM/)
  await s.find(p=>p.children==='Check suggested times').props.onClick();s.render()
  assert.match(s.text(),/10:00 AM/);assert.equal(calls.length,2)
  const unavailable=await screen('SuggestedTimes',async()=>{throw Object.assign(new Error('inactive'),{code:'operating_rules_required'})},
    false,async()=>{},{...props})
  await unavailable.find(p=>p.children==='Check suggested times').props.onClick();unavailable.render()
  assert.match(unavailable.text(),/preferred-time request for CookCredit review/)
  assert.equal(unavailable.find(p=>p.children==='Check suggested times').props.disabled,false)
})

test('malformed suggestion responses never display or select an unverified time',async()=>{
  const s=await screen('SuggestedTimes',async()=>({...suggestions(),reservesTime:true}),false,async()=>{},
    {date:'2026-12-01',service:'cooking',durationMinutes:120,onChoose:()=>assert.fail('unexpected choice')})
  await s.find(p=>p.children==='Check suggested times').props.onClick();s.render()
  assert.match(s.text(),/could not read these suggestions/);assert.doesNotMatch(s.text(),/10:00 AM/)
})

test('visit steps preserve a preferred time, submit only on Send, and require a new time after timezone changes',async()=>{
  const calls=[],id='11111111-1111-4111-8111-111111111111'
  const s=await screen('RequestVisit',async(path,options)=>{calls.push([path,options]);return path==='/household'?{household:null}:{id}},
    false,async()=>{},{profile:{consentVersion:'home-visit-v2',consentText:'Example consent',serviceTimeZone:'America/New_York',serviceStates:['GA']}})
  await s.settle()
  const submit=values=>s.find((p,n)=>n.type==='form').props.onSubmit({preventDefault(){},currentTarget:values})
  await submit({});s.render();await submit({});s.render()
  s.find(p=>p.name==='date').props.onChange({target:{value:'2026-12-01'}});s.render()
  let choice=s.find(p=>typeof p.onChoose==='function')
  choice.props.onChoose('14:00');s.render();assert.equal(calls.length,1)
  s.find(p=>p.children==='Back').props.onClick();s.render();await submit({});s.render()
  assert.equal(s.find(p=>p.name==='time').props.value,'14:00')
  choice=s.find(p=>typeof p.onTimeZone==='function');choice.props.onTimeZone('UTC');s.render()
  assert.equal(s.find(p=>p.name==='time').props.value,'');assert.match(s.text(),/Choose your preferred start time again/)
  s.find(p=>p.name==='time').props.onChange({target:{value:'15:00'}});s.render()
  await submit({cooking:'120',date:'2026-12-01',time:'15:00',street:'100 Example Street',unit:'Unit 2',city:'Atlanta',state:'GA',postalCode:'30315',repeatPreference:'once',notes:'',preferences:[],consent:'on'})
  s.render();assert.equal(calls.length,2);assert.equal(calls[1][0],'/visits')
  assert.equal(calls[1][1].body.timeZone,'UTC');assert.equal(calls[1][1].body.time,'15:00')
  assert.equal(s.location.hash,'visit/'+id)
})

test('optional suggestion fallback leaves manual request fields outside the boundary and preserves explicit submission',async()=>{
  const calls=[]
  const s=await screen('RequestVisit',async(path,options)=>{calls.push([path,options]);return path==='/household'?{household:null}:{id:'saved-visit'}},
    false,async()=>{},{profile:{consentVersion:'home-visit-v2',consentText:'Synthetic consent',serviceTimeZone:'America/New_York',serviceStates:['GA']}})
  await s.settle()
  const submit=body=>s.find((p,n)=>n.type==='form').props.onSubmit({preventDefault(){},currentTarget:body})
  await submit({});s.render();await submit({});s.render()
  s.find(p=>p.name==='date').props.onChange({target:{value:'2030-01-07'}})
  s.find(p=>p.name==='time').props.onChange({target:{value:'14:00'}});s.render()
  const boundary=s.find((p,n)=>n.type==='home-boundary')
  assert.ok(boundary)
  const nodes=n=>!n||typeof n!=='object'?[]:[n,...(Array.isArray(n.props?.children)?n.props.children:[n.props?.children]).flatMap(nodes)]
  assert.equal(nodes(boundary).some(n=>['address','date','time','consent'].includes(n.props?.name)),false)
  const fallback=boundary.props.fallback({reference:'synthetic-reference'})
  assert.match(JSON.stringify(fallback),/Choose your preferred date and time above/)
  assert.match(JSON.stringify(fallback),/No time has been verified or reserved/)
  assert.match(JSON.stringify(fallback),/synthetic-reference/)
  assert.equal(calls.length,1)
  assert.equal(s.find(p=>p.name==='date').props.value,'2030-01-07')
  assert.equal(s.find(p=>p.name==='time').props.value,'14:00')
  await submit({cooking:'120',date:'2030-01-07',time:'14:00',street:'100 Example Street',unit:'Unit 2',city:'Atlanta',state:'GA',postalCode:'30315',repeatPreference:'once',notes:'',preferences:[],consent:'on'})
  assert.equal(calls.length,2);assert.equal(calls[1][0],'/visits')
  assert.equal(calls[1][1].body.time,'14:00')
  assert.equal(s.location.hash,'visit/saved-visit')
})


test('postal fields and weekly preference use one existing visit command and one explicit household save',async()=>{
  const calls=[];
  const s=await screen('RequestVisit',async(path,options)=>{calls.push([path,options]);return options?{id:'saved-visit'}:{household:null}},false);
  await s.settle();
  const submit=values=>s.find((p,n)=>n.type==='form').props.onSubmit({preventDefault(){},currentTarget:values});
  await submit({});s.render();await submit({});s.render();
  assert.equal(s.find(p=>p.name==='street').props.autoComplete,'section-visit address-line1');
  assert.equal(s.find(p=>p.name==='postalCode').props.inputMode,'numeric');
  await submit({cooking:'120',date:'2030-01-07',time:'10:00',street:'100 Example Street',unit:'Unit 2',city:'Atlanta',state:'GA',postalCode:'30315',repeatPreference:'weekly',notes:'',consent:'on',remember:'on'});
  assert.deepEqual(calls.map(([path,options])=>[path,options?.method]),[['/household',undefined],['/visits','POST'],['/household','PUT']]);
  assert.equal(calls[1][1].body.address,'100 Example Street, Unit 2, Atlanta, GA 30315');
  assert.equal(calls[1][1].body.repeatPreference,'weekly');
  assert.deepEqual(calls[1][1].body.addressDetails,calls[2][1].body.addressDetails);
  assert.equal('repeatPreference' in calls[2][1].body,false);
  assert.equal(s.location.hash,'visit/saved-visit');
});


test('owner price creation preserves cent precision and failed parsing creates no pricing request',async()=>{
  const calls=[];
  const actual=await readFile(new URL('../home/api.js',import.meta.url),'utf8');
  const dollars=vm.runInNewContext('('+actual.match(/export function dollars\(value\) \{[\s\S]*?\n\}/)[0].replace('export ', '')+')');
  const s=await screen('Team',async(path,options)=>{calls.push([path,options]);return path==='/enrollments'?{enrollments:[]}:{activeId:null,versions:[]}},true,async()=>{},
    {profile:{owner:true,operator:true,enrollmentOnly:true}},'default',{modules:{'../api':{api:async(path,options)=>{calls.push([path,options]);return path==='/enrollments'?{enrollments:[]}:{activeId:null,versions:[]}},dollars,label:v=>v,money:String}}});
  await s.settle();s.find((p,n)=>n.type==='button'&&p.children==='Pricing').props.onClick();s.render();await s.settle();
  const submit=values=>s.find((p,n)=>n.type==='form').props.onSubmit({preventDefault(){},currentTarget:values});
  submit({cooking:'45.25',cleaning:'35.10',fee:'10.00',commission:'15.00',cap:'100.00',validity:'1440'});await s.settle();
  const saved=calls.find(([path,options])=>path==='/pricing'&&options?.method==='POST');
  assert.equal(saved[1].body.rates.cookingHourlyCents,4525);assert.equal(saved[1].body.rates.cleaningHourlyCents,3510);
  const count=calls.filter(([,options])=>options?.method==='POST').length;
  submit({cooking:'45.999',cleaning:'35.10',fee:'10',commission:'15',cap:'100',validity:'1440'});await s.settle();
  assert.equal(calls.filter(([,options])=>options?.method==='POST').length,count);
  assert.match(s.text(),/no more than two decimal places/);
});

test('customer worklist uses private search, versioned follow-up and honest copy recovery',async()=>{
  const timers=[],calls=[];let saved=false
  const person={id:'u:member',kind:'customer',customerId:'member',name:'Jordan Smith',email:'member@example.test',
    service:'both',canContact:true,status:'new',version:3,activityAt:'2026-11-02T12:00:00+00:00',callbackCount:0,visitCount:0}
  const s=await screen('CustomerWorklist',async(path,options)=>{
    calls.push([path,options]);if(path.endsWith('/follow-up')){saved=true;return {updated:true}}
    return {people:saved?[]:[person],nextCursor:null}
  },true,async()=>{throw new Error('Clipboard unavailable')},{},'default',{
    context:{setTimeout(fn){timers.push(fn);return timers.length},clearTimeout(){}}})
  timers.shift()();await s.settle()
  assert.equal(calls.length,1);assert.equal(calls[0][0],'/enrollments/search')
  assert.equal(calls[0][1].method,'POST');assert.equal(calls[0][1].body.scope,'needs')
  assert.match(s.text(),/Jordan Smith/);assert.match(s.text(),/Cooking and cleaning/)
  await s.find(p=>p.children==='Copy enrollment link').props.onClick();s.render()
  assert.match(s.text(),/Select the enrollment link/);assert.doesNotMatch(s.text(),/link copied/)
  assert.equal(s.find(p=>p.readOnly).props.value,'https://home.example.test/#enroll')
  await s.find(p=>p['aria-label']==='Follow-up for Jordan Smith').props.onChange({target:{value:'done'}});s.render()
  assert.equal(calls[1][0],'/enrollments/member/follow-up')
  assert.equal(JSON.stringify(calls[1][1].body),JSON.stringify({status:'done',version:3,activityAt:person.activityAt}))
  assert.match(s.text(),/No one is waiting/)
})

test('a late customer search cannot overwrite the latest query or invent a saved status',async()=>{
  const timers=[],pending=[]
  const s=await screen('CustomerWorklist',async(path,options)=>new Promise(resolve=>pending.push({resolve,query:options.body.query})),
    true,async()=>{},{},'default',{context:{setTimeout(fn){timers.push(fn);return timers.length},clearTimeout(){}}})
  timers.shift()()
  s.find(p=>p.placeholder==='Name, email or phone').props.onChange({target:{value:'New name'}});s.render()
  timers.shift()()
  assert.equal(pending[1].query,'New name')
  pending[1].resolve({people:[],nextCursor:null});await s.settle()
  pending[0].resolve({people:[{id:'c:old',kind:'callback',name:'Outdated contact',activityAt:'2026-11-01',callbackCount:0}],nextCursor:null});await s.settle()
  assert.match(s.text(),/No match/);assert.doesNotMatch(s.text(),/Outdated contact/)
})

test('a saved visit with a failed remember request shows its acknowledgement and cannot be resent from the form',async()=>{
  const calls=[],savedId='11111111-1111-4111-8111-111111111111';let acknowledged=0
  const s=await screen('RequestVisit',async(path,options)=>{
    calls.push([path,options]);if(path==='/visits')return {id:savedId}
    if(options)throw new Error('Saved address unavailable')
    return {household:null}
  },false,async()=>{},{onSubmitted:()=>{acknowledged++}})
  await s.settle()
  const form=()=>s.find((p,n)=>n.type==='form')
  await form().props.onSubmit({preventDefault(){},currentTarget:{}});s.render()
  await form().props.onSubmit({preventDefault(){},currentTarget:{}});s.render()
  await form().props.onSubmit({preventDefault(){},currentTarget:{cooking:'120',street:'100 Example Street',city:'Atlanta',state:'GA',postalCode:'30315',date:'2030-01-07',time:'10:00',repeatPreference:'once',notes:'',consent:'on',remember:'on'}});s.render()
  assert.equal(acknowledged,1);assert.equal(form(),undefined)
  assert.match(s.text(),/Your request is saved/);assert.match(s.text(),/couldn’t also save/)
  assert.equal(s.find(p=>p.children==='View my request').props.href,'#visit/'+savedId)
  assert.equal(calls.filter(([path])=>path==='/visits').length,1)
})

test('request choices match the selected service and saved-detail errors do not block a manual request',async()=>{
  let fail=true,reads=0
  const s=await screen('RequestVisit',async()=>{reads++;if(fail)throw new Error('Unavailable');return {household:null}},false)
  await s.settle();assert.match(s.text(),/saved details could not load/)
  assert.ok(s.find(p=>p.name==='preferences'&&p.value==='allergies'))
  assert.equal(s.find(p=>p.name==='preferences'&&p.value==='customer_supplies'),undefined)
  const cleaning=s.find((p,n)=>n.type==='label'&&Array.isArray(p.children)&&p.children.includes('Cleaning'))
  cleaning.props.children.find(n=>n?.type==='input').props.onChange();s.render()
  assert.ok(s.find(p=>p.name==='preferences'&&p.value==='customer_supplies'))
  assert.equal(s.find(p=>p.name==='preferences'&&p.value==='allergies'),undefined)
  fail=false;await s.find(p=>p.children==='Try saved details again').props.onClick();s.render()
  assert.equal(reads,2);assert.doesNotMatch(s.text(),/saved details could not load/)
})

test('service-interest removal needs an explicit second action and can be cancelled without a write',async()=>{
  const writes=[]
  const s=await screen('Enrollment',async(path,options)=>{if(options){writes.push(options.method);return {removed:true}}return {enrollment:{service:'both',name:'Jordan Smith'}}},false)
  await s.settle();s.find(p=>p.children==='Remove my service needs').props.onClick();s.render()
  assert.equal(writes.length,0);assert.match(s.text(),/existing visits will stay saved/)
  s.find(p=>p.children==='Keep my service needs').props.onClick();s.render();assert.equal(writes.length,0)
  s.find(p=>p.children==='Remove my service needs').props.onClick();s.render()
  await s.find(p=>p.children==='Confirm removal').props.onClick();s.render()
  assert.deepEqual(writes,['DELETE']);assert.match(s.text(),/service interest and its phone number have been removed/)
})
