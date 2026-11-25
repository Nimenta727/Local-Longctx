import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { join } from 'node:path'
import { resolve } from 'node:path'

const { chromium } = await import(process.env.FARSTACK_PLAYWRIGHT ?? 'playwright')
const browser = await chromium.launch({ executablePath: process.env.FARSTACK_CHROMIUM, args: ['--no-sandbox'] })
try {
  const page = await browser.newPage({ viewport: { width: 1320, height: 940 }, deviceScaleFactor: 1 })
  const errors = []
  page.on('pageerror', error=>errors.push(error.message))
  page.on('console', message=>{if(message.type()==='error')errors.push(message.text())})
  const sources=new Set(['index.html','workspace.css','workspace.mjs','farstack.png'])
  const types={html:'text/html',css:'text/css',mjs:'text/javascript',png:'image/png'}
  await page.route('https://farstack.test/**', async route=>{
    const name=new URL(route.request().url()).pathname.slice(1)||'index.html'
    if(!sources.has(name))return route.fulfill({status:404,body:''})
    return route.fulfill({contentType:types[name.split('.').at(-1)],
      body:await readFile(join(import.meta.dirname,'../app',name))})
  })
  await page.addInitScript(()=>{
    const limits=(value,step,min,max,unit_bytes)=>({value,step,min,max,unit_bytes,adjustable:true})
    let geometry={
      pools:{
        kv_tokens:limits(32768,1024,1024,98304,65536),
        moe_experts:limits(64,1,32,256,12582912),
        swa_tokens:limits(6144,1024,2048,16384,24576),
      },
      native_window:131072,budget_bytes:6*2**30,active_requests:0,profile:'default',revision:'initial',
      vram_free_gib:3.2,vram_total_gib:12,ram_free_gib:8.4,ram_total_gib:32,prefill_tps:386,decode_tps:32,
    }
    const settings={context:8192,modelLimit:32768,output:1024,ratio:.8,experimentalSsd:false}
    const calls=[]
    Object.assign(window,{fixture:{calls,active:n=>{geometry.active_requests=n},external:()=>{geometry.revision='external'}},farstack:{
      status:async()=>({phase:'ready',model:'Qwen3-30B-A3B-Q4_K_M.gguf',bundled:true,settings,fixture:true}),
      cacheStatus:async()=>structuredClone(geometry),
      cacheApply:async draft=>{
        calls.push(draft)
        if(draft.revision!==geometry.revision)throw new Error('inconsistent revision')
        for(const [name,value] of Object.entries(draft.changes))geometry.pools[name].value=value
        geometry={...geometry,revision:'applied',profile:'saved'}
        return {applied:true,snapshot:structuredClone(geometry),profile:'saved'}
      },
      saveStartup:async values=>{Object.assign(settings,values);calls.push({startup:values})
        return {phase:'ready',model:'Qwen3-30B-A3B-Q4_K_M.gguf',bundled:true,settings,fixture:true}},
      conversations:async()=>[],
      onDelta:()=>{},
    }})
  })
  await page.goto('https://farstack.test/')
  await page.getByRole('slider',{name:'KV 缓存',exact:true}).waitFor()
  await page.screenshot({path:resolve(process.env.FARSTACK_SCREENSHOT??'/tmp/farstack-workspace.png')})
  const kv=page.locator('#pool-kv_tokens')
  const initial=await kv.inputValue()
  const thumb=await kv.boundingBox()
  const before=await page.locator('#cache-cost').textContent()
  await page.mouse.move(thumb.x+thumb.width*.33,thumb.y+thumb.height/2)
  await page.mouse.down()
  await page.mouse.move(thumb.x+thumb.width*.47,thumb.y+thumb.height/2,{steps:10})
  await page.mouse.up()
  const dragged=await kv.inputValue()
  assert.notEqual(dragged,initial)
  assert.notEqual(await page.locator('#cache-cost').textContent(),before)
  assert.equal((await page.evaluate(()=>window.fixture.calls)).length,0)
  await page.locator('#cache-apply').click()
  await page.getByText('容量已保存',{exact:true}).waitFor()
  assert.equal(await kv.inputValue(),dragged)
  assert.deepEqual((await page.evaluate(()=>window.fixture.calls))[0],{revision:'initial',changes:{kv_tokens:Number(dragged)}})
  await kv.focus()
  await kv.press('End')
  assert.equal(await page.locator('#cache-apply').isDisabled(),true)
  await page.getByText('超过组合显存预算',{exact:false}).waitFor()
  await page.locator('#cache-reset').click()
  assert.equal(await kv.inputValue(),dragged)
  await page.getByRole('button',{name:/轻量/}).click()
  assert.equal(await kv.inputValue(),'4096')
  await page.evaluate(()=>window.fixture.active(1))
  await page.getByText('当前有活跃请求',{exact:false}).waitFor()
  assert.equal(await page.locator('#cache-apply').isDisabled(),true)
  await page.evaluate(()=>{window.fixture.active(0);window.fixture.external()})
  await page.getByText('引擎配置已改变',{exact:false}).waitFor()
  assert.equal(await page.locator('#cache-apply').isDisabled(),true)
  await page.locator('#cache-reset').click()
  await page.locator('#startup summary').click()
  assert.equal(await page.locator('#startup-activeKv').count(),0)
  const context=page.locator('#startup-context')
  await context.press('Home')
  assert.equal(await context.inputValue(),'1024')
  assert.ok(Number(await page.locator('#startup-output').inputValue())<=767)
  await page.locator('#startup-experimentalSsd').check()
  await page.locator('#startup-activeKv').check()
  const disk=page.locator('#startup-activeKvDisk')
  await disk.focus()
  await disk.press('ArrowRight')
  assert.equal(await disk.inputValue(),'4160')
  await page.locator('#save-startup').click()
  await page.getByText('启动参数已保存',{exact:true}).waitFor()
  const saved=(await page.evaluate(()=>window.fixture.calls)).at(-1).startup
  assert.equal(saved.activeKv,true)
  assert.equal(saved.activeKvDisk,4160)
  assert.equal(saved.context,1024)
  assert.ok(saved.output<=767)
  await page.getByRole('button',{name:'本地会话'}).click()
  await page.getByRole('heading',{name:'本地会话'}).waitFor()
  await page.getByRole('button',{name:'模型与缓存'}).click()
  await page.setViewportSize({width:780,height:900})
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true)
  assert.deepEqual(errors,[])
  console.log('Rendered Chromium: pointer drag, memory budget, apply/read-back, request/revision gates, SSD settings and responsive navigation passed')
} finally { await browser.close() }
