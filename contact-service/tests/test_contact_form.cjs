const assert = require('node:assert/strict');
const {test} = require('node:test');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const code = fs.readFileSync(path.resolve(__dirname, '../../public-site/contact-form.js'), 'utf8');
function fixture(fetch) {
 const listeners = {}; const fields = [{disabled:false},{disabled:false}];
 const button = {disabled:false,textContent:'Send message'};
 const status = {textContent:'',focus(){}};
 const form = {dataset:{endpoint:'https://contact.test/api/contact'},
  reportValidity:()=>true, querySelector:()=>button, querySelectorAll:()=>fields,
  addEventListener:(event,fn)=>listeners[event]=fn, resets:0, reset(){this.resets++}};
 let id=0;
 vm.runInNewContext(code,{document:{getElementById:id=>id==='contact-form'?form:status},
 crypto:{randomUUID:()=>String(++id)},FormData:class {constructor(){return [['email','test@example.com'],['message','Test text']]}},
 AbortController,fetch,setTimeout,clearTimeout,TypeError});
 return {form,fields,button,status,listeners,submit:()=>listeners.submit({preventDefault(){}})};
}
test('server acceptance clears the form and restores controls',async()=>{
 const f=fixture(async()=>({ok:true,json:async()=>({sent:true})}));await f.submit();
 assert.equal(f.form.resets,1);assert.match(f.status.textContent,/has been sent/);
 assert.equal(f.button.disabled,false);assert.ok(f.fields.every(x=>!x.disabled));
});
test('server rejection retains content and the same retry identifier',async()=>{
 const calls=[];const f=fixture(async(url,options)=>{calls.push(JSON.parse(options.body));return {ok:false,json:async()=>({error:'Delivery unconfirmed'})}});
 await f.submit();await f.submit();assert.equal(f.form.resets,0);
 assert.equal(calls[0].requestId,calls[1].requestId);assert.equal(f.status.textContent,'Delivery unconfirmed');
 f.listeners.input();await f.submit();assert.notEqual(calls[2].requestId,calls[1].requestId);
});
test('network failure cannot report success or erase the message',async()=>{
 const f=fixture(async()=>{throw new TypeError('Network unavailable')});await f.submit();
 assert.equal(f.form.resets,0);assert.match(f.status.textContent,/could not confirm/);assert.equal(f.button.disabled,false);
});
test('double submission and in-flight edits are prevented',async()=>{
 let finish,calls=0;const f=fixture(()=>{calls++;return new Promise(resolve=>finish=resolve)});
 const pending=f.submit();assert.ok(f.fields.every(x=>x.disabled));await f.submit();assert.equal(calls,1);
 finish({ok:true,json:async()=>({sent:true})});await pending;
});
test('HTTP 200 without explicit acceptance is still an error',async()=>{
 const f=fixture(async()=>({ok:true,json:async()=>({})}));await f.submit();assert.equal(f.form.resets,0);assert.match(f.status.textContent,/could not confirm/);
});
