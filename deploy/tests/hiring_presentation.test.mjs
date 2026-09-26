import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
const deploy=fileURLToPath(new URL('../',import.meta.url));
const code=JSON.parse(execFileSync('python',['-c','import json; from hiring_simple_overlay import PRESENTATION_JS; print(json.dumps(PRESENTATION_JS))'],{cwd:deploy,encoding:'utf8'}));
function setup(){
 const nodes=Object.fromEntries(['hiring-company-name','hiring-role-title','hiring-instructions','hiring-company-logo','m-subject'].map(id=>[id,{textContent:'',value:'',removeAttribute(key){delete this[key];}}]));
 const ctx={$:id=>nodes[id],URL};vm.createContext(ctx);vm.runInContext(code,ctx);return {nodes,render:ctx.renderHiringPresentation};
}
test('employer text is rendered literally and missing logo falls back to company name',()=>{
 const {nodes,render}=setup();render({companyName:'Kitchen A',instructions:'<img src=x onerror=alert(1)>'});
 assert.equal(nodes['hiring-instructions'].textContent,'<img src=x onerror=alert(1)>');assert.equal(nodes['hiring-company-logo'].hidden,true);
 assert.equal(nodes['hiring-company-name'].textContent,'Kitchen A');
});
for(const url of ['javascript:alert(1)','data:image/svg+xml,abc','http://example.test/a','https://name:pass@example.test/a']) test(`rejects unsafe logo ${url.split(':')[0]}`,()=>{
 const {nodes,render}=setup();render({logoUrl:url});assert.equal(nodes['hiring-company-logo'].src,undefined);
});
test('HTTPS logo failure stays unobtrusive and typed applicant name is preserved',()=>{
 const {nodes,render}=setup();nodes['m-subject'].value='My name';render({logoUrl:'https://example.test/a.png',applicantName:'Other'});
 assert.equal(nodes['m-subject'].value,'My name');assert.equal(nodes['hiring-company-logo'].referrerPolicy,'no-referrer');
 nodes['hiring-company-logo'].onload();assert.equal(nodes['hiring-company-logo'].hidden,false);
 nodes['hiring-company-logo'].onerror();assert.equal(nodes['hiring-company-logo'].hidden,true);
});
test('account name prefills empty input only',()=>{const {nodes,render}=setup();render({applicantName:'Applicant A'});assert.equal(nodes['m-subject'].value,'Applicant A');});
