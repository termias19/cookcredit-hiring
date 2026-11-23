import test from 'node:test'
import assert from 'node:assert/strict'
import {createPendingRequests} from '../home/pendingRequests.js'

function fixture() { const values=new Map();return {values,getItem:key=>values.get(key),setItem:(key,value)=>values.set(key,value)} }
const command=(body={address:'Synthetic private address',instructions:'Synthetic private instruction'})=>
  ({uid:'synthetic-person',method:'POST',path:'/visits',body})

test('unknown outcome survives a client reload without storing household payload or identity',async()=>{
  const storage=fixture(),first=createPendingRequests({storage:()=>storage})
  const a=await first.reserve(command()),reloaded=createPendingRequests({storage:()=>storage})
  const b=await reloaded.reserve(command());assert.equal(a.key,b.key)
  const serialized=[...storage.values.values()].join('')
  for(const privateValue of ['Synthetic','address','instructions','synthetic-person','/visits'])assert.equal(serialized.includes(privateValue),false)
  reloaded.acknowledge(b)
  assert.equal(JSON.parse([...storage.values.values()][0]).length,0)
})

test('account changes and changed requests never reuse an unrelated pending key',async()=>{
  const store=createPendingRequests({storage:()=>fixture()})
  const a=await store.reserve(command()),b=await store.reserve({...command(),uid:'another-person'})
  const c=await store.reserve(command({address:'Another synthetic address'}))
  assert.notEqual(a.key,b.key);assert.notEqual(a.key,c.key)
})

test('a late concurrent preparation reuses the acknowledged key; a later deliberate command gets a fresh one',async()=>{
  let at=100;const store=createPendingRequests({storage:()=>fixture(),now:()=>at})
  const a=await store.reserve({...command(),startedAt:100});at=110;store.acknowledge(a)
  const concurrent=await store.reserve({...command(),startedAt:105});assert.equal(concurrent.key,a.key)
  at=120;const next=await store.reserve({...command(),startedAt:120});assert.notEqual(next.key,a.key)
})

test('same-name same-size changed receipt uses the content hash, not file metadata',async()=>{
  const store=createPendingRequests({storage:()=>fixture()})
  const photo=content=>({get:()=>({name:'receipt.png',size:4,arrayBuffer:async()=>new TextEncoder().encode(content).buffer})})
  const a=await store.reserve({...command(),form:true,body:photo('aaaa')})
  const b=await store.reserve({...command(),form:true,body:photo('bbbb')})
  assert.notEqual(a.key,b.key)
})

test('unavailable storage preserves same-page retries and reports the durability limit',async()=>{
  const store=createPendingRequests({storage:()=>{throw new Error('storage disabled')}})
  const a=await store.reserve(command()),b=await store.reserve(command())
  assert.equal(a.key,b.key);assert.equal(a.durable,false)
})

test('aborted preparation does not reserve or persist a mutation',async()=>{
  const storage=fixture(),store=createPendingRequests({storage:()=>storage}),controller=new AbortController();controller.abort()
  await assert.rejects(store.reserve({...command(),signal:controller.signal}),{name:'AbortError'})
  assert.equal(storage.values.size,0)
})

test('unresolved references are bounded without evicting a request whose outcome is unknown',async()=>{
  const store=createPendingRequests({storage:()=>fixture()}),first=await store.reserve(command({n:0}))
  for(let i=1;i<60;i++)await store.reserve(command({n:i}))
  await assert.rejects(store.reserve(command({n:60})),/unfinished requests/)
  assert.equal((await store.reserve(command({n:0}))).key,first.key)
})
