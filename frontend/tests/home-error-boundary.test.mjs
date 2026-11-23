import test from 'node:test'
import assert from 'node:assert/strict'
import {readFile} from 'node:fs/promises'
import vm from 'node:vm'
import React from 'react'
import * as jsx from 'react/jsx-runtime'
import {renderToStaticMarkup} from 'react-dom/server'
import {transformWithEsbuild} from 'vite'
import * as homeNavigation from '../home/navigation.js'

// Exercise the actual boundary class and real React elements, without replacing
// hooks or performing browser navigation, requests, authentication or payments.
async function boundary(props={},environment={}) {
  const reports=[],logs=[],actions=[]
  const source=await readFile(new URL('../home/HomeErrorBoundary.jsx',import.meta.url),'utf8')
  const {code}=await transformWithEsbuild(source,'HomeErrorBoundary.jsx',{loader:'jsx',jsx:'automatic',format:'cjs',
    define:{'import.meta.env':JSON.stringify(environment)}})
  const modules={react:React,'react/jsx-runtime':jsx,'./navigation':homeNavigation,'../src/utils/errorReporting':{
    reportClientError:(...args)=>{reports.push(args);return 'synthetic-reference'},
  }}
  const location={hash:'#request',reload(){actions.push('reload')},assign(url){actions.push(url)}}
  const context={module:{exports:{}},require:id=>modules[id],location,
    console:{error:(...args)=>logs.push(args)},fetch(){assert.fail('The boundary must not submit a request')}}
  vm.runInNewContext(code,context)
  const Boundary=context.module.exports.default
  const instance=new Boundary({children:React.createElement('p',null,'Original screen'),...props})
  instance.setState=update=>{instance.state={...instance.state,...(typeof update==='function'?update(instance.state,instance.props):update)}}
  const nodes=node=>node==null||node===false?[]:Array.isArray(node)?node.flatMap(nodes):[node,...nodes(node.props?.children)]
  const find=label=>nodes(instance.render()).find(n=>n?.props?.children===label)
  const html=()=>renderToStaticMarkup(instance.render())
  const fail=error=>{instance.setState(Boundary.getDerivedStateFromError(error));instance.componentDidCatch(error)}
  return {instance,location,logs,reports,actions,find,html,fail}
}

test('a missing lazy module offers a manual latest-version reload without automatic retry or saved-data claims',async()=>{
  const s=await boundary()
  assert.match(s.html(),/Original screen/)
  const privateError=new TypeError('Failed to fetch dynamically imported module: https://private.example/assets/private-name.js')
  s.fail(privateError)
  const html=s.html()
  assert.match(html,/Part of this page couldn’t load/)
  assert.match(html,/Reload latest version/)
  assert.match(html,/Reloading clears unsent form entries/)
  assert.match(html,/check My visits before sending it again/)
  assert.match(html,/Support reference: synthetic-reference/)
  assert.doesNotMatch(html,/Your saved visit|private\.example|private-name/)
  assert.deepEqual(s.actions,[])
  assert.deepEqual(s.reports,[['render_error']])
  assert.deepEqual(s.logs,[['CookCredit Home screen unavailable (home_ui_module_load_failed)']])
  s.html();assert.deepEqual(s.actions,[])
  s.find('Reload latest version').props.onClick()
  assert.deepEqual(s.actions,['reload'])
  assert.equal(s.location.hash,'#request')
  assert.deepEqual(s.reports,[['render_error']])
})

test('an optional feature fallback reuses the real boundary without offering a form-destroying reload',async()=>{
  let received
  const s=await boundary({fallback:({reference})=>{
    received=reference
    return React.createElement('section',null,
      React.createElement('p',null,'Suggested times unavailable. Choose a preferred time for review.'),
      React.createElement('small',null,reference))
  }})
  s.fail(new TypeError('Failed to fetch dynamically imported module: https://private.example/chunk.js'))
  assert.match(s.html(),/Suggested times unavailable/)
  assert.equal(received,'synthetic-reference')
  assert.equal(s.find('Reload latest version'),undefined)
  assert.equal(s.find('Return Home'),undefined)
  assert.deepEqual(s.actions,[])
  assert.deepEqual(s.reports,[['render_error']])
})

test('ordinary render failures stay neutral and Return Home changes route before restoring the screen',async()=>{
  const s=await boundary();s.fail(new Error('Synthetic private household detail'))
  assert.match(s.html(),/We couldn’t open that screen/)
  assert.doesNotMatch(s.html(),/private household|Your saved visit|site update/)
  assert.deepEqual(s.logs,[['CookCredit Home screen unavailable (home_ui_render_failed)']])
  s.find('Return Home').props.onClick()
  assert.equal(s.location.hash,'home')
  assert.match(s.html(),/Original screen/)
  assert.deepEqual(s.actions,[])
})

test('browser module errors use only bounded local classifications and keep brand navigation manual',async()=>{
  for(const message of ['Importing a module script failed.', 'error loading dynamically imported module: https://private.example/module.js']){
    const s=await boundary();s.fail(new TypeError(message))
    assert.equal(s.instance.state.moduleFailure,true)
    assert.deepEqual(s.reports,[['render_error']])
    let prevented=false
    s.find('CookCredit Home').props.onClick({preventDefault(){prevented=true}})
    assert.equal(prevented,true);assert.equal(s.location.hash,'home')
    assert.deepEqual(s.actions,[])
  }
})

test('production error recovery uses the same public Home overview without forwarding private routes',async()=>{
  const s=await boundary({}, {PROD:true});s.fail(new Error('Synthetic failure'))
  assert.match(s.html(),/href="https:\/\/cookcredit.com\/home\/"/)
  s.find('Return Home').props.onClick()
  assert.deepEqual(s.actions,['https://cookcredit.com/home/'])
})
