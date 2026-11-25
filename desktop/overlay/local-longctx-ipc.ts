/** Local runtime bridge. Executable and working directory are owned by the main process. */
import { app, clipboard, dialog, ipcMain, shell, type IpcMainInvokeEvent, type BrowserWindow } from 'electron'
import { spawn, type ChildProcess } from 'node:child_process'
import { randomBytes } from 'node:crypto'
import { mkdir, readFile, writeFile, rename, rm, stat, lstat } from 'node:fs/promises'
import { basename, dirname, join, resolve } from 'node:path'

type Phase='idle'|'starting'|'ready'|'stopping'|'error'
const PREFIX='local-longctx:'
const integer=(v:unknown,min:number,max:number):number=>{
  if(typeof v!=='number'||!Number.isInteger(v)||v<min||v>max) throw new Error('Invalid integer setting')
  return v
}
const moeStrategies=['auto','offload','fused','cpu','hybrid']
const positive=(value:unknown, fallback:number, label:string):number=>{
  const v=value===undefined?fallback:value
  if(typeof v!=='number'||!Number.isFinite(v)||v<=0)throw new Error('Invalid '+label)
  return v
}

export function installLocalLongctx(owner:(event:IpcMainInvokeEvent)=>BrowserWindow):void {
  let phase:Phase='idle',detail=''
  let model:string|null=null,engine:string|null=null
  let ssdDirectory:string|null=null
  let child:ChildProcess|undefined
  let key='',context=0,output=0
  let operation=false
  const root=app.isPackaged?join(process.resourcesPath,'farstack-runtime'):process.env.LOCAL_LONGCTX_DEV_ROOT
  const python=app.isPackaged&&root?join(root,'python.exe'):process.env.LOCAL_LONGCTX_PYTHON
  if(app.isPackaged&&python)engine=python
  const stateDir=join(app.getPath('userData'),'local-longctx')
  const config=join(stateDir,'config.json')
  let settings:Record<string,unknown>|undefined
  let activeSettings:ReturnType<typeof startupDraft>['settings']|undefined
  const restoreSettings=async()=>{
    try {
      const saved=JSON.parse(await readFile(config,'utf8')) as Record<string,unknown>
      if(typeof saved.ssd_active_kv_dir==='string')ssdDirectory=saved.ssd_active_kv_dir
      if(typeof saved.model==='string'&&saved.model.toLowerCase().endsWith('.gguf')&&await stat(saved.model).then(s=>s.isFile(),()=>false))model=saved.model
      if(!app.isPackaged&&typeof saved.freetoken_server==='string'&&!/\.(bat|cmd|ps1|sh)$/i.test(saved.freetoken_server)&&await stat(saved.freetoken_server).then(s=>s.isFile(),()=>false))engine=saved.freetoken_server
      if(typeof saved.context==='number'&&typeof saved.model_limit==='number'&&typeof saved.output_reserve==='number'&&typeof saved.threads==='number'&&typeof saved.freetoken_memory_ratio==='number'&&typeof saved.kv_cache_dtype==='string'&&typeof saved.kv_tokens==='number'&&typeof saved.expert_slots==='number'&&typeof saved.ubatch==='number'){
        settings={context:saved.context,modelLimit:saved.model_limit,output:saved.output_reserve,threads:saved.threads,ratio:saved.freetoken_memory_ratio,dtype:saved.kv_cache_dtype,kvTokens:saved.kv_tokens,expertSlots:saved.expert_slots,prefill:saved.ubatch,
          moeStrategy:saved.moe_strategy??'auto',minVram:saved.freetoken_min_vram_gib??4,
          vramHeadroom:saved.vram_headroom_gib??1,ramHeadroom:saved.ram_headroom_gib??2,
          hostWeights:saved.host_weights_gib??null,ssdExpertOffload:saved.ssd_expert_offload===true,
          ssdKvCheckpoint:saved.ssd_kv_checkpoint===true,experimentalSsd:saved.experimental_ssd===true,
          ssdExpertStagingMib:saved.ssd_expert_staging_mib??4,ssdKvLimitMib:saved.ssd_kv_limit_mib??256,
          activeKv:saved.ssd_active_kv===true,activeKvRam:saved.ssd_active_kv_ram_mib??256,
          activeKvGpu:saved.ssd_active_kv_gpu_tokens??1024,activeKvDisk:saved.ssd_active_kv_disk_mib??4096}
      }
    } catch(error) {
      if(!(error instanceof Error&&'code' in error&&error.code==='ENOENT'))detail='Saved inference settings could not be read'
    }
  }
  const restored=restoreSettings()
  const profileKey=async()=>{
    const path=join(stateDir,'gateway.key')
    try{await writeFile(path,randomBytes(32).toString('hex'),{flag:'wx',mode:0o600})}
    catch(error){if(!(error instanceof Error&&'code' in error&&error.code==='EEXIST'))throw error}
    const info=await lstat(path)
    if(!info.isFile()||(process.platform!=='win32'&&(info.mode&0o077)!==0))throw new Error('Unsafe local gateway key file')
    const saved=await readFile(path,'utf8')
    if(!/^[0-9a-f]{64}$/.test(saved))throw new Error('Invalid local gateway key file')
    return saved
  }
  const status=()=>({phase,detail,settings,activeSettings,bundled:app.isPackaged,ssdDirectory,
    model:model===null?null:basename(model),engine:app.isPackaged?'FreeToken':engine===null?null:basename(engine)})
  const ensureIdle=()=>{if(operation||child||['starting','ready','stopping'].includes(phase))throw new Error('Engine is busy')}
  ipcMain.handle(PREFIX+'status',async event=>{owner(event);await restored;return status()})
  ipcMain.handle(PREFIX+'open-data',async event=>{
    owner(event)
    const error=await shell.openPath(dirname(app.getPath('userData')))
    if(error)throw new Error(error)
  })
  ipcMain.handle(PREFIX+'pick-ssd',async event=>{
    const window=owner(event);await restored
    if(operation||phase==='starting'||phase==='stopping')throw new Error('Engine is busy')
    operation=true
    try{
      const selected=await dialog.showOpenDialog(window,{properties:['openDirectory'],title:'Choose a folder on your SSD'})
      if(!selected.canceled&&selected.filePaths.length===1)ssdDirectory=resolve(selected.filePaths[0]!)
      return status()
    }finally{operation=false}
  })
  ipcMain.handle(PREFIX+'pick',async(event,kind:unknown)=>{
    const window=owner(event);await restored;ensureIdle()
    if(kind!=='model'&&kind!=='engine')throw new Error('Invalid file kind')
    if(app.isPackaged&&kind==='engine')throw new Error('FarStack uses the bundled engine')
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
  const startupDraft=(raw:unknown)=>{
    if(!model||!engine||typeof raw!=='object'||raw===null)throw new Error('Select model and engine first')
    const s=raw as Record<string,unknown>
    const ctx=integer(s.context,1024,1000000),limit=integer(s.modelLimit,ctx,2097152)
    const out=integer(s.output,1,ctx-257),threads=integer(s.threads,1,1024)
    if(s.verified!==true||typeof s.ratio!=='number'||!Number.isFinite(s.ratio)||s.ratio<.1||s.ratio>.95||typeof s.dtype!=='string'||!['auto','int8_per_token_head','fp8_per_token_head'].includes(s.dtype))throw new Error('Invalid or unverified configuration')
    const kvTokens=integer(s.kvTokens??0,0,2097152),expertSlots=integer(s.expertSlots??0,0,1000000)
    const prefill=integer(s.prefill??512,1,ctx)
    const moeStrategy=s.moeStrategy??'auto'
    if(typeof moeStrategy!=='string'||!moeStrategies.includes(moeStrategy))throw new Error('Invalid MoE strategy')
    const experimentalSsd=s.experimentalSsd===undefined?false:s.experimentalSsd
    if(typeof experimentalSsd!=='boolean')throw new Error('Invalid experimental SSD setting')
    const ssdExpertOffload=s.ssdExpertOffload===undefined?false:s.ssdExpertOffload
    if(typeof ssdExpertOffload!=='boolean')throw new Error('Invalid SSD expert offload setting')
    if(experimentalSsd&&ssdExpertOffload&&moeStrategy!=='offload')throw new Error('SSD expert offload requires MoE strategy offload')
    const ssdKvCheckpoint=s.ssdKvCheckpoint===undefined?false:s.ssdKvCheckpoint
    if(typeof ssdKvCheckpoint!=='boolean')throw new Error('Invalid SSD KV checkpoint setting')
    if(experimentalSsd&&ssdKvCheckpoint&&s.dtype!=='auto')throw new Error('SSD KV checkpoint requires Auto KV precision')
    const ssdExpertStagingMib=integer(s.ssdExpertStagingMib??4,4,32)
    const ssdKvLimitMib=integer(s.ssdKvLimitMib??256,16,1024)
    const activeKv=s.activeKv===undefined?false:s.activeKv
    if(typeof activeKv!=='boolean'||(experimentalSsd&&activeKv&&(!app.isPackaged||s.dtype!=='auto'||ssdKvCheckpoint)))
      throw new Error('Active SSD KV requires the bundled engine, Auto KV precision and disabled KV checkpoints')
    const activeKvRam=integer(s.activeKvRam??256,0,8192)
    const activeKvGpu=integer(s.activeKvGpu??1024,0,65536)
    const activeKvDisk=integer(s.activeKvDisk??4096,64,65536)
    const minVram=positive(s.minVram,4,'minimum free VRAM')
    const vramHeadroom=positive(s.vramHeadroom,1,'VRAM headroom')
    const ramHeadroom=positive(s.ramHeadroom,2,'RAM headroom')
    const hostWeights=s.hostWeights==null?null:positive(s.hostWeights,0,'host weights estimate')
    return {
      config:{freetoken_server:engine,bundled_engine:app.isPackaged,model,model_id:'local-longctx',model_is_moe:true,freetoken_model_verified:true,
        context:ctx,model_limit:limit,logical_target:1000000,output_reserve:out,threads,ubatch:prefill,
        kv_tokens:kvTokens,expert_slots:expertSlots,freetoken_memory_ratio:s.ratio,kv_cache_dtype:s.dtype,state_dir:stateDir,
        moe_strategy:moeStrategy,freetoken_min_vram_gib:minVram,vram_headroom_gib:vramHeadroom,
        ram_headroom_gib:ramHeadroom,host_weights_gib:hostWeights,ssd_expert_offload:ssdExpertOffload,
        experimental_ssd:experimentalSsd,ssd_kv_checkpoint:ssdKvCheckpoint,
        ssd_expert_staging_mib:ssdExpertStagingMib,ssd_kv_limit_mib:ssdKvLimitMib,
        ssd_active_kv:activeKv,ssd_active_kv_dir:ssdDirectory,ssd_active_kv_ram_mib:activeKvRam,
        ssd_active_kv_gpu_tokens:activeKvGpu,ssd_active_kv_disk_mib:activeKvDisk},
      settings:{context:ctx,modelLimit:limit,output:out,threads,ratio:s.ratio,dtype:s.dtype,kvTokens,expertSlots,prefill,
        moeStrategy,minVram,vramHeadroom,ramHeadroom,hostWeights,experimentalSsd,
        ssdExpertOffload,ssdKvCheckpoint,ssdExpertStagingMib,ssdKvLimitMib,activeKv,activeKvRam,activeKvGpu,activeKvDisk},
    }
  }
  const writeConfig=async (draft:ReturnType<typeof startupDraft>)=>{
    await mkdir(stateDir,{recursive:true,mode:0o700})
    const temporary=config+'.'+randomBytes(8).toString('hex')+'.tmp'
    try{
      await writeFile(temporary,JSON.stringify(draft.config,null,2),{flag:'wx',mode:0o600})
      await rename(temporary,config)
    }finally{await rm(temporary,{force:true})}
    settings=draft.settings
  }
  ipcMain.handle(PREFIX+'save-startup',async(event,raw:unknown)=>{
    owner(event);await restored
    if(operation||phase==='starting'||phase==='stopping')throw new Error('Engine is busy')
    const draft=startupDraft(raw)
    operation=true
    try{await writeConfig(draft);return status()}finally{operation=false}
  })
  ipcMain.handle(PREFIX+'start',async(event,raw:unknown)=>{
    const window=owner(event);await restored;ensureIdle()
    if(!root||!python||(app.isPackaged&&!await stat(python).then(info=>info.isFile(),()=>false)))
      throw new Error('FarStack runtime is missing from this installation')
    const draft=startupDraft(raw)
    const {context:ctx,output:out}=draft.settings
    operation=true
    try{
      if(!app.isPackaged){
        const approved=await dialog.showMessageBox(window,{type:'question',buttons:['Cancel','Start trusted local engine'],defaultId:0,cancelId:0,message:'Start selected executable?',detail:draft.config.freetoken_server+'\n'+draft.config.model})
        if(approved.response!==1)return status()
      }
      await mkdir(stateDir,{recursive:true,mode:0o700})
      const nextKey=await profileKey()
      await writeConfig(draft)
      key=nextKey;context=ctx;output=out
      activeSettings=draft.settings
      phase='starting';detail=''
      const workerArgs=[...(app.isPackaged?['-I']:[]),'-m','longctx.desktop_worker',config]
      const proc=spawn(python,workerArgs,{cwd:root,shell:false,windowsHide:true,env:{...process.env,LOCAL_LONGCTX_API_KEY:key},stdio:['pipe','ignore','ignore']})
      child=proc
      proc.stdin?.on('error',()=>{})
      proc.once('error',()=>{if(child===proc){child=undefined;key='';activeSettings=undefined;phase='error';detail='Worker failed to start'}})
      proc.once('exit',(code,signal)=>{
        if(child!==proc)return
        child=undefined;key='';activeSettings=undefined
        if(phase==='stopping'&&detail===''&&code===0){phase='idle';return}
        phase='error'
        if(!detail)detail='Worker exited ('+String(code??signal)+'); inspect local logs'
      })
      void (async()=>{
        const deadline=Date.now()+1800000
        while(child===proc&&phase==='starting'&&Date.now()<deadline){
          try{
            const response=await fetch('http://127.0.0.1:18080/local/desktop/capabilities',{headers:{Authorization:'Bearer '+key},signal:AbortSignal.timeout(2000),redirect:'error'})
            if(response.ok){
              const data=await response.json() as {worker_pid?:number;context?:{configured_native_window?:number;output_reserve?:number}}
              const nativeWindow=data.context?.configured_native_window
              const reserve=data.context?.output_reserve
              if(child===proc&&phase==='starting'&&proc.pid!==undefined&&data.worker_pid===proc.pid
                &&typeof nativeWindow==='number'&&typeof reserve==='number'&&
                (app.isPackaged?nativeWindow<=ctx&&reserve<=out:nativeWindow===ctx&&reserve===out)){
                context=nativeWindow;output=reserve
                activeSettings={...draft.settings,context,output}
                phase='ready';return
              }
            }
          }catch{ /* Startup polling only. */ }
          await new Promise(r=>setTimeout(r,1000))
        }
        if(child===proc&&phase==='starting'){detail='Startup timeout';phase='stopping';proc.stdin?.end()}
      })()
      return status()
    }finally{operation=false}
  })
  ipcMain.handle(PREFIX+'copy-key',event=>{
    owner(event)
    if(phase!=='ready'||!key)throw new Error('Start engine first')
    clipboard.writeText(key)
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
      changes[name]=integer(value,0,Number.MAX_SAFE_INTEGER)
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
