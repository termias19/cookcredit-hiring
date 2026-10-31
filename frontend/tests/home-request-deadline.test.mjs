import test from 'node:test'
import assert from 'node:assert/strict'
import {waitForRequest} from '../home/waitForRequest.js'
import {createPendingRequests} from '../home/pendingRequests.js'
import {readFileSync} from 'node:fs'
import vm from 'node:vm'

const source=readFileSync(new URL('../home/api.js',import.meta.url),'utf8')
  .replace(/^import .*;\r?\n/gm,'').replace(/export /g,'')
function client(prepare,overrides={}) {
  const calls=[],reports=[]
  let expire,cleared=false
  const sandbox={
    auth:{currentUser:null},getAppCheckHeaders:prepare,waitForRequest,createPendingRequests,
    reportClientError:code=>reports.push(code),saveHiringFile:()=>{},
    AbortController,DOMException,crypto,
    setTimeout:callback=>{expire=callback;return 1},clearTimeout:()=>{cleared=true},
    fetch:async(...args)=>{calls.push(args);if(overrides.offline)throw new TypeError('offline');return {ok:true,json:async()=>({ok:true})}},
  }
  if(overrides.storage)sandbox.createPendingRequests=()=>createPendingRequests({storage:()=>overrides.storage})
  vm.runInNewContext(source+';globalThis.request=api;',sandbox)
  return {request:sandbox.request,calls,reports,expire:()=>expire(),cleared:()=>cleared}
}

test('actual Home client never submits a mutation after security preparation times out',async()=>{
  let finish
  const clientUnderTest=client(()=>new Promise(resolve=>{finish=resolve}))
  const operation=clientUnderTest.request('/callbacks',{method:'POST',body:{name:'Synthetic'},protectedAccount:true})
  await Promise.resolve();await Promise.resolve()
  clientUnderTest.expire()
  await assert.rejects(operation,/security check did not finish/)
  finish({'X-Firebase-AppCheck':'late-synthetic-token'})
  await Promise.resolve();await Promise.resolve()
  assert.equal(clientUnderTest.calls.length,0)
  assert.deepEqual(clientUnderTest.reports,['api_timeout'])
  assert.equal(clientUnderTest.cleared(),true)
})

test('actual Home client keeps rejected attestation private and does not submit',async()=>{
  const error=Object.assign(new Error('synthetic provider internals'),{code:'appCheck/recaptcha-error'})
  const clientUnderTest=client(()=>Promise.reject(error))
  await assert.rejects(clientUnderTest.request('/callbacks',{method:'POST',body:{},protectedAccount:true}),e=>
    /security check could not finish/.test(e.message)&&!e.message.includes('provider internals'))
  assert.equal(clientUnderTest.calls.length,0)
  assert.deepEqual(clientUnderTest.reports,['unhandled_error'])
})

test('actual Home client attaches completed attestation before the existing API request',async()=>{
  const clientUnderTest=client(()=>Promise.resolve({'X-Firebase-AppCheck':'synthetic-token'}))
  await clientUnderTest.request('/callbacks',{method:'POST',body:{name:'Synthetic'},protectedAccount:true})
  assert.equal(clientUnderTest.calls.length,1)
  const [url,options]=clientUnderTest.calls[0]
  assert.equal(url,'/api/home/callbacks')
  assert.equal(options.headers['X-Firebase-AppCheck'],'synthetic-token')
  assert.match(options.headers['Idempotency-Key'],/^[a-f0-9-]{36}$/)
  assert.equal(clientUnderTest.cleared(),true)
})

test('callback UI nonce changes after reload do not duplicate an unacknowledged callback',async()=>{
  const values=new Map(),storage={getItem:key=>values.get(key),setItem:(key,value)=>values.set(key,value)}
  const first=client(async()=>({}),{storage,offline:true})
  await assert.rejects(first.request('/callbacks',{method:'POST',body:{requestId:'old-ui-nonce',name:'Synthetic',phone:'555'}}))
  const second=client(async()=>({}),{storage})
  await second.request('/callbacks',{method:'POST',body:{requestId:'new-ui-nonce',name:'Synthetic',phone:'555'}})
  const a=first.calls[0][1],b=second.calls[0][1]
  assert.equal(a.headers['Idempotency-Key'],b.headers['Idempotency-Key'])
  assert.equal(JSON.parse(a.body).requestId,JSON.parse(b.body).requestId)
  assert.equal(JSON.parse(b.body).requestId,b.headers['Idempotency-Key'])
})

test('expired request does not start token preparation',async()=>{
  const controller=new AbortController();controller.abort()
  let started=0
  await assert.rejects(waitForRequest(()=>{started++;return 'token'},controller.signal),{name:'AbortError'})
  assert.equal(started,0)
})

test('late security preparation cannot issue a request after cancellation',async()=>{
  const controller=new AbortController()
  let finish,requests=0
  const prepared=new Promise(resolve=>{finish=resolve})
  const operation=(async()=>{
    await waitForRequest(()=>prepared,controller.signal)
    requests++
  })()
  await Promise.resolve()
  controller.abort()
  await assert.rejects(operation,{name:'AbortError'})
  finish('late-token')
  await Promise.resolve();await Promise.resolve()
  assert.equal(requests,0)
})

test('ready preparation succeeds and provider rejection is preserved',async()=>{
  const controller=new AbortController()
  assert.equal(await waitForRequest(()=>Promise.resolve('ready'),controller.signal),'ready')
  const error=new Error('synthetic provider failure')
  await assert.rejects(waitForRequest(()=>Promise.reject(error),controller.signal),e=>e===error)
  controller.abort()
})

test('abort during preparation wins over an already resolved value',async()=>{
  const controller=new AbortController()
  await assert.rejects(waitForRequest(()=>{controller.abort();return 'late'},controller.signal),{name:'AbortError'})
})
