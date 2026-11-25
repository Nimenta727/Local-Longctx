import assert from 'node:assert/strict'
import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const { _electron } = await import(process.env.FARSTACK_PLAYWRIGHT ?? 'playwright')
const data = await mkdtemp(join(tmpdir(),'farstack-shell-'))
let app
try {
  app=await _electron.launch({
    executablePath: process.env.FARSTACK_ELECTRON,
    args:[...(process.platform==='linux'?['--no-sandbox','--disable-gpu','--ozone-platform=headless']:[]),join(import.meta.dirname,'..')],
    env:{...process.env,FARSTACK_USER_DATA:data},
  })
  const page=await app.firstWindow()
  const errors=[]
  page.on('pageerror',error=>errors.push(error.message))
  await page.getByRole('heading',{name:'模型与缓存'}).waitFor()
  assert.match(page.url(),/^farstack:\/\/workspace\//)
  const status=await page.evaluate(()=>window.farstack.status())
  assert.equal(status.phase,'idle')
  assert.equal(status.model,null)
  assert.equal(await page.locator('#engine-action').isDisabled(),true)
  assert.equal(await page.getByRole('button',{name:'选择 FreeToken'}).isVisible(),true)
  assert.equal(await page.locator('#cache-controls').isVisible(),false)
  if(process.env.FARSTACK_ELECTRON_SCREENSHOT)await page.screenshot({path:process.env.FARSTACK_ELECTRON_SCREENSHOT})
  await page.getByRole('button',{name:'本地会话'}).click()
  await page.getByText('暂无本地记录').waitFor()
  assert.deepEqual(errors,[])
  console.log('Electron rendered the first-party workspace and resolved secure preload IPC')
} finally {
  await app?.close()
  await rm(data,{recursive:true,force:true})
}
