import test from 'node:test'
import assert from 'node:assert/strict'
import {readFile} from 'node:fs/promises'
import vm from 'node:vm'
import {transformWithEsbuild} from 'vite'

// Actual screen handlers under controlled failures; browser acceptance is separate.
async function screen(name,api,owner=true,clipboard=async()=>{},props={}) {
  const states=[],effects=[];let index,tree,queued
  const react={lazy:()=> 'lazy-screen',Suspense:'suspense',useState(initial){const slot=index++;if(!(slot in states))states[slot]=initial;
    return [states[slot],value=>{states[slot]=typeof value==='function'?value(states[slot]):value}]},
    useRef(initial){const slot=index++;return states[slot]||=( {current:initial} )},
    useEffect(fn,deps){const slot=index++,old=effects[slot];if(!old||deps.some((d,i)=>d!==old.deps[i]))
      queued.push(()=>{old?.cleanup?.();effects[slot]={deps,cleanup:fn()}})}}
  const jsx=(type,props)=>({type,props})
  const modules={react,'react/jsx-runtime':{jsx,jsxs:jsx,Fragment:'fragment'},
    '../api':{api,label:v=>v,money:v=>String(v),dollars:Number},
    '../../api':{api,label:v=>v,money:v=>String(v),dollars:Number},
    './Enrollment':{serviceNames:{both:'Cooking and cleaning',cooking:'Cooking',cleaning:'Cleaning',not_sure:'Help choosing'}},
    './OperatingRulesDraft':{__esModule:true,default:()=>null}}
  const source=await readFile(new URL(`../home/screens/${name}.jsx`,import.meta.url),'utf8')
  const {code}=await transformWithEsbuild(source,name+'.jsx',{loader:'jsx',jsx:'automatic',format:'cjs'})
  const context={module:{exports:{}},require:id=>modules[id],URL,window:{scrollTo(){}},
    location:{href:'https://home.example.test/#team'},navigator:{clipboard:{writeText:clipboard}},
    FormData:class {constructor(values){this.values=values}has(key){return this.values[key]===true}get(key){return this.values[key]??null}}}
  vm.runInNewContext(code,context)
  const Component=context.module.exports.default
  function render(){index=0;queued=[];tree=Component({profile:{owner,email:'member@example.test'},...props});queued.forEach(fn=>fn())}
  function nodes(node){if(node==null||node===false)return [];if(Array.isArray(node))return node.flatMap(nodes);
    return [node,...nodes(node.props?.children)]}
  const text=()=>nodes(tree).filter(n=>typeof n==='string'||typeof n==='number').join(' ')
  const find=predicate=>nodes(tree).find(n=>n?.props&&predicate(n.props,n))
  async function settle(){await new Promise(resolve=>setImmediate(resolve));render()}
  render();return {render,settle,text,find}
}

test('enrollment load errors retry instead of displaying empty or successful enrollment',async()=>{
  let fail=true
  const s=await screen('Enrollment',async()=>{if(fail)throw new Error('Connection lost');return {enrollment:null}})
  await s.settle();assert.match(s.text(),/Connection lost/)
  assert.equal(s.find((p,n)=>n.type==='form'),undefined)
  fail=false;s.find(p=>p.children==='Try again').props.onClick();s.render();await s.settle()
  assert.ok(s.find((p,n)=>n.type==='form'))
})

test('enrollment save uses the existing account endpoint and only claims success after acknowledgement',async()=>{
  const calls=[];let fail=true
  const s=await screen('Enrollment',async(path,options)=>{calls.push([path,options]);
    if(!options)return {enrollment:null};if(fail)throw new Error('Retry safely');return {enrollment:{service:'both'}}})
  await s.settle()
  s.find(p=>p.value==='both').props.onChange();s.render()
  const submit=()=>s.find((p,n)=>n.type==='form').props.onSubmit({preventDefault(){},currentTarget:{contactConsent:true}})
  await submit();s.render();assert.match(s.text(),/Retry safely/);assert.doesNotMatch(s.text(),/You’re on the list/)
  fail=false;await submit();s.render();assert.match(s.text(),/You’re on the list/)
  assert.equal(calls.length,3)
  assert.equal(calls[2][0],'/enrollment');assert.equal(calls[2][1].method,'PUT')
  assert.equal(JSON.stringify(calls[2][1].body),JSON.stringify({service:'both',phone:'',contactConsent:true}))
})

test('only the owner screen requests the enrollment directory and failed copy stays honest',async()=>{
  const calls=[]
  const api=async path=>{calls.push(path);return path==='/enrollments'?{enrollments:[]}:{visits:[]}}
  const operator=await screen('Team',api,false);await operator.settle()
  assert.deepEqual(calls,['/visits']);assert.doesNotMatch(operator.text(),/People enrolled/)
  const owner=await screen('Team',api,true,async()=>{throw new Error('clipboard blocked')});await owner.settle()
  assert.equal(calls.at(-1),'/enrollments')
  assert.match(owner.text(),/People enrolled/)
  await owner.find(p=>p.children==='Copy enrollment link').props.onClick();owner.render()
  assert.match(owner.text(),/link was not copied/)
  assert.equal(owner.find(p=>p.readOnly).props.value,'https://home.example.test/#enroll')
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
  await enrollment.find((p,n)=>n.type==='form').props.onSubmit({preventDefault(){},currentTarget:{contactConsent:true}})
  enrollment.render()
  enrollment.find(p=>p.href==='#request').props.onClick()
  assert.equal(chosen,'both')
  const visit=await screen('RequestVisit',async()=>({household:null}),false,async()=>{},{initialService:chosen})
  await visit.settle()
  assert.equal(visit.find(p=>p.name==='cleaning').props.defaultValue,'60')
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
