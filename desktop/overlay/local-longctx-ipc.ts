/** Local-only development bridge. Never accepts executable paths or command lines from renderer. */
import { app, dialog, ipcMain, type IpcMainInvokeEvent, type BrowserWindow } from 'electron'
import { spawn, type ChildProcess } from 'node:child_process'
import { randomBytes } from 'node:crypto'
import { mkdir, writeFile, rename, stat } from 'node:fs/promises'
import { basename, join, resolve } from 'node:path'

type Phase='idle'|'starting'|'ready'|'stopping'|'error'
const PREFIX='local-longctx:'
const integer=(v:unknown,min:number,max:number):number=>{
  if(typeof v!=='number'||!Number.isInteger(v)||v<min||v>max) throw new Error('Invalid integer setting')
  return v
}
export function installLocalLongctx(owner:(event:IpcMainInvokeEvent)=>BrowserWindow):void {
  let phase:Phase='idle',detail=''
  let model:string|null=null,engine:string|null=null
  let child:ChildProcess|undefined
  let key='',context=0,output=0
  let operation=false
  const root=process.env.LOCAL_LONGCTX_DEV_ROOT
  const python=process.env.LOCAL_LONGCTX_PYTHON
  const status=()=>({phase,detail,model:model===null?null:basename(model),engine:engine===null?null:basename(engine)})
  const ensureIdle=()=>{if(operation||child||['starting','ready','stopping'].includes(phase))throw new Error('Engine is busy')}
  ipcMain.handle(PREFIX+'status',event=>{owner(event);return status()})
  ipcMain.handle(PREFIX+'pick',async(event,kind:unknown)=>{
    const window=owner(event);ensureIdle()
    if(kind!=='model'&&kind!=='engine')throw new Error('Invalid file kind')
    operation=true
    try{
      const selected=await dialog.showOpenDialog(window,{properties:['openFile'],title:kind==='model'?'Select local MoE GGUF':'Select a trusted FreeToken executable',...(kind==='model'?{filters:[{name:'GGUF',extensions:['gguf']}]}:{})})
      if(!selected.canceled&&selected.filePaths.length===1){
        const path=resolve(selected.filePaths[0]!)
        if(!(await stat(path)).isFile())throw new Error('Not a regular file')
        if(kind==='model') {if(!path.toLowerCase().endsWith('.gguf'))throw new Error('GGUF required');model=path}
        else {if(/\.(bat|cmd|ps1|sh)$/i.test(path))throw new Error('Use a trusted executable, not a shell script');engine=path}
      }
      return status()
    }finally{operation=false}
  })
  ipcMain.handle(PREFIX+'start',async(event,raw:unknown)=>{
    const window=owner(event);ensureIdle()
    if(app.isPackaged||!root||!python)throw new Error('Local-Longctx development runtime is not configured')
    if(!model||!engine||typeof raw!=='object'||raw===null)throw new Error('Select model and engine first')
    const s=raw as Record<string,unknown>
    const ctx=integer(s.context,1024,1000000),limit=integer(s.modelLimit,ctx,2097152)
    const out=integer(s.output,1,ctx-257),threads=integer(s.threads,1,1024)
    if(s.verified!==true||typeof s.ratio!=='number'||!Number.isFinite(s.ratio)||s.ratio<.1||s.ratio>.95||typeof s.dtype!=='string'||!['auto','int8_per_token_head','fp8_per_token_head'].includes(s.dtype))throw new Error('Invalid or unverified configuration')
    const kvTokens=integer(s.kvTokens??0,0,2097152),expertSlots=integer(s.expertSlots??0,0,1000000)
    const prefill=integer(s.prefill??512,1,ctx)
    operation=true
    try{
      const approved=await dialog.showMessageBox(window,{type:'question',buttons:['Cancel','Start trusted local engine'],defaultId:0,cancelId:0,message:'Start selected executable?',detail:engine+'\n'+model})
      if(approved.response!==1)return status()
      const stateDir=join(app.getPath('userData'),'local-longctx')
      await mkdir(stateDir,{recursive:true,mode:0o700})
      const config=join(stateDir,'config.json')
      const body={freetoken_server:engine,model,model_id:'local-longctx',model_is_moe:true,freetoken_model_verified:true,context:ctx,model_limit:limit,logical_target:1000000,output_reserve:out,threads,ubatch:prefill,kv_tokens:kvTokens,expert_slots:expertSlots,freetoken_memory_ratio:s.ratio,kv_cache_dtype:s.dtype,state_dir:stateDir}
      await writeFile(config+'.tmp',JSON.stringify(body,null,2),{mode:0o600})
      await rename(config+'.tmp',config)
      key=randomBytes(32).toString('hex');context=ctx;output=out
      phase='starting';detail=''
      const proc=spawn(python,['-m','longctx.desktop_worker',config],{cwd:root,shell:false,windowsHide:true,env:{...process.env,LOCAL_LONGCTX_API_KEY:key},stdio:['pipe','ignore','ignore']})
      child=proc
      proc.stdin?.on('error',()=>{})
      proc.once('error',()=>{if(child===proc){child=undefined;key='';phase='error';detail='Worker failed to start'}})
      proc.once('exit',code=>{if(child===proc){child=undefined;key='';phase=phase==='stopping'?'idle':'error';detail=phase==='error'?'Worker exited ('+String(code)+'); inspect local logs':''}})
      void (async()=>{
        const deadline=Date.now()+1800000
        while(child===proc&&phase==='starting'&&Date.now()<deadline){
          try{
            const response=await fetch('http://127.0.0.1:18080/local/desktop/capabilities',{headers:{Authorization:'Bearer '+key},signal:AbortSignal.timeout(2000),redirect:'error'})
            if(response.ok){
              const data=await response.json() as {context?:{configured_native_window?:number;output_reserve?:number}}
              if(child===proc&&phase==='starting'&&data.context?.configured_native_window===ctx&&data.context.output_reserve===out){phase='ready';return}
            }
          }catch{ /* Startup polling only. */ }
          await new Promise(r=>setTimeout(r,1000))
        }
        if(child===proc&&phase==='starting'){detail='Startup timeout';phase='stopping';proc.stdin?.end()}
      })()
      return status()
    }finally{operation=false}
  })
  ipcMain.handle(PREFIX+'stop',event=>{owner(event);if(operation)throw new Error('Maintenance in progress');if(child){phase='stopping';child.stdin?.end()}return status()})
  ipcMain.handle(PREFIX+'connection',event=>{
    owner(event);if(phase!=='ready'||!key)throw new Error('Start engine first')
    return {model:'local-longctx',baseURL:'http://127.0.0.1:18080',key,context,output}
  })
  const cacheRequest=async(path:string,body?:unknown)=>{
    if(phase!=='ready'||!key)throw new Error('Engine not ready')
    const response=await fetch('http://127.0.0.1:18080'+path,{
      method:body===undefined?'GET':'POST',redirect:'error',
      headers:{Authorization:'Bearer '+key,'Content-Type':'application/json'},
      ...(body===undefined?{}:{body:JSON.stringify(body)}),
      signal:AbortSignal.timeout(body===undefined?7000:320000)
    })
    if(!response.ok)throw new Error('Cache request rejected: HTTP '+response.status)
    return response.json()
  }
  ipcMain.handle(PREFIX+'cache-status',event=>{owner(event);return cacheRequest('/local/cache/status')})
  ipcMain.handle(PREFIX+'cache-apply',async(event,raw:unknown)=>{
    const window=owner(event)
    if(operation||phase!=='ready'||typeof raw!=='object'||raw===null)throw new Error('Engine busy or invalid request')
    const data=raw as {revision?:unknown;changes?:unknown}
    if(typeof data.revision!=='string'||!/^[a-f0-9]{64}$/.test(data.revision)||typeof data.changes!=='object'||data.changes===null)throw new Error('Invalid cache draft')
    const changes:Record<string,number>={}
    for(const [name,value] of Object.entries(data.changes)){
      if(!['kv_tokens','moe_experts','swa_tokens','mamba_slots'].includes(name))throw new Error('Invalid cache field')
      changes[name]=integer(value,0,2097152)
    }
    if(!Object.keys(changes).length)throw new Error('No cache change')
    operation=true
    try{
      const ok=await dialog.showMessageBox(window,{type:'warning',buttons:['Cancel','Rebuild idle cache'],defaultId:0,cancelId:0,
        message:'Resize native cache pools? Prefix reuse may be lost.',detail:JSON.stringify(changes)})
      if(ok.response!==1)return null
      return await cacheRequest('/local/cache/apply',{revision:data.revision,changes,confirm:true})
    }finally{operation=false}
  })
  app.on('will-quit',()=>{child?.stdin?.end()})
}
