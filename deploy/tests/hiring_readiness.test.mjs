import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
const deploy=fileURLToPath(new URL('../',import.meta.url));
const [helpers,verify]=JSON.parse(execFileSync('python',['-c',
 'import json; from hiring_readiness_overlay import HELPERS, VERIFY; print(json.dumps([HELPERS,VERIFY]))'],{cwd:deploy,encoding:'utf8'}));
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};};
async function ticks(){for(let i=0;i<15;i++)await Promise.resolve();}
function setup(){
 const timers=new Map(),events=[],node={textContent:''};let id=0;
 const context={state:{hiring:{returnUrl:'https://example.test/application'},hiringSessionVerified:false},
  cloudLibrary:{user:{uid:'a'},getAppCheckToken:async()=> 'app-check',getIdToken:async()=> 'id-token'},
  getHiringSession:async()=>({status:'started'}),syncHiringAuthState:()=>{},friendlyCloudError:()=> 'Session unavailable',
  reportClientIssue:async(...args)=>events.push(args),$:()=>node,
  setTimeout:fn=>{timers.set(++id,fn);return id;},clearTimeout:n=>timers.delete(n),
  window:{setTimeout:fn=>{timers.set(++id,fn);return id;},location:{assign:()=>events.push('redirect')}},
 };
 vm.createContext(context);vm.runInContext(helpers+'\n'+verify,context);
 return {context,timers,events,node,run:()=>context.verifyHiringAccess()};
}
test('readiness requires both real security and session checks',async()=>{
 const c=setup(),calls=[];
 c.context.cloudLibrary.getAppCheckToken=async()=>calls.push('security');
 c.context.cloudLibrary.getIdToken=async()=>{calls.push('auth');return 'id';};
 c.context.getHiringSession=async()=>{calls.push('session');return {status:'started'};};
 await c.run();assert.deepEqual(calls,['security','auth','session']);
 assert.equal(c.context.state.hiringSessionVerified,true);assert.equal(c.timers.size,0);
});
test('App Check throttle is visible, reports no secrets and cannot authorize capture',async()=>{
 const c=setup();c.context.cloudLibrary.getAppCheckToken=async()=>{throw Object.assign(Error('secret-token'),{code:'appCheck/throttled'});};
 c.context.getHiringSession=async()=>assert.fail('must not reach session');
 await assert.rejects(c.run());assert.match(c.context.state.hiringVerificationError,/CC-HIRING-APPCHECK/);
 assert.equal(c.context.state.hiringSessionVerified,false);
 assert.equal(JSON.stringify(c.events).includes('secret-token'),false);
});
for(const phase of ['security','auth','session'])test(`${phase} hang ends at deadline and late result cannot mark ready`,async()=>{
 const c=setup(),pending=deferred();
 if(phase==='security')c.context.cloudLibrary.getAppCheckToken=()=>pending.promise;
 if(phase==='auth')c.context.cloudLibrary.getIdToken=()=>pending.promise;
 if(phase==='session')c.context.getHiringSession=()=>pending.promise;
 const done=c.run();const rejection=assert.rejects(done,e=>e.code==='hiring/readiness-timeout');
 await ticks();for(const fire of [...c.timers.values()])fire();await rejection;
 pending.resolve({status:'started'});await ticks();
 assert.equal(c.context.state.hiringSessionVerified,false);assert.match(c.context.state.hiringVerificationError,/CC-HIRING-TIMEOUT/);
 assert.equal(c.timers.size,0);
});
test('account change fences a late success',async()=>{
 const c=setup(),pending=deferred();c.context.getHiringSession=()=>pending.promise;
 const done=c.run();await ticks();c.context.cloudLibrary.user={uid:'b'};
 pending.resolve({status:'started'});await done;assert.equal(c.context.state.hiringSessionVerified,false);
});
test('retry success cannot be overwritten by an older failure',async()=>{
 const c=setup(),pending=deferred();c.context.getHiringSession=()=>pending.promise;
 const first=c.run();await ticks();c.context.getHiringSession=async()=>({status:'started'});
 await c.run();pending.reject(Error('old'));await first;
 assert.equal(c.context.state.hiringSessionVerified,true);assert.equal(c.context.state.hiringVerificationError,'');
});
test('expired or submitted sessions do not authorize recording',async()=>{
 for(const status of ['expired','completed','processing']){
  const c=setup();c.context.getHiringSession=async()=>({status});
  if(status==='expired')await assert.rejects(c.run());else await c.run();
  assert.equal(c.context.state.hiringSessionVerified,false);
 }
});
