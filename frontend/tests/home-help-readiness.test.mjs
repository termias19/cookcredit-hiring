import test from 'node:test'
import assert from 'node:assert/strict'
import vm from 'node:vm'
import {readFile} from 'node:fs/promises'
import {transformWithEsbuild} from 'vite'
import * as homeNavigation from '../home/navigation.js'
import * as customerWorklist from '../home/customerWorklist.js'
const {safeHomeRoute}=homeNavigation

test('actual Home callback form warms security without submitting data and respects private access gates',async()=>{
  const source=await readFile(new URL('../home/App.jsx',import.meta.url),'utf8')
  const {code}=await transformWithEsbuild(source+'\nexport {Help};','App.jsx',{
    loader:'jsx',jsx:'automatic',format:'cjs',define:{'import.meta.env':'{}'},
  })
  for(const props of [
    {privateAcceptance:false},
    {privateAcceptance:true,user:undefined},
    {privateAcceptance:true,user:{emailVerified:false}},
    {privateAcceptance:true,user:{emailVerified:true}},
    {privateAcceptance:false,accessErrorCode:'private_acceptance'},
  ]){
    let warmed=0,submitted=0
    const effects=[]
    const react={lazy:()=>null,useState:value=>[value,()=>{}],useRef:value=>({current:value}),useEffect:fn=>effects.push(fn)}
    const jsx=(type,props)=>({type,props})
    const modules={react,'react/jsx-runtime':{jsx,jsxs:jsx},
      '../src/firebase':{auth:{},getAppCheckHeaders:async()=>{warmed++;throw new Error('synthetic warm-up failure')}},
      './api':{api:async()=>{submitted++}},
      './navigation':homeNavigation,
      './customerWorklist':customerWorklist,
    }
    const context={module:{exports:{}},require:id=>modules[id]||{},crypto}
    vm.runInNewContext(code,context)
    context.module.exports.Help(props)
    effects.forEach(fn=>fn())
    await Promise.resolve();await Promise.resolve()
    const eligible=!props.accessErrorCode&&(!props.privateAcceptance||props.user?.emailVerified)
    assert.equal(warmed,eligible?1:0)
    assert.equal(submitted,0,'Opening Help must never submit contact details or create a callback')
  }
})
