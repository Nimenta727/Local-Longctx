const api = window.farstack
const $ = id => document.getElementById(id)
const number = n => Number(n).toLocaleString('zh-CN')
const gib = n => (n / 2 ** 30).toFixed(2) + ' GiB'
const node = (tag, text, className) => {
  const element = document.createElement(tag)
  if (text !== undefined) element.textContent = text
  if (className) element.className = className
  return element
}
const defaults = {
  context:8192,modelLimit:32768,output:1024,threads:8,ratio:.8,dtype:'auto',
  kvTokens:0,expertSlots:0,prefill:512,moeStrategy:'auto',minVram:4,vramHeadroom:1,ramHeadroom:2,
  experimentalSsd:false,ssdExpertOffload:false,ssdKvCheckpoint:false,ssdExpertStagingMib:4,ssdKvLimitMib:256,
  activeKv:false,activeKvRam:256,activeKvGpu:1024,activeKvDisk:4096,
}
const labels = {
  kv_tokens:['KV 缓存','为注意力保留的 Token','tokens'],
  moe_experts:['MoE 专家缓存','显存中常驻的专家槽位','槽'],
  swa_tokens:['滑窗 KV','滑动窗口层的缓存容量','tokens'],
  mamba_slots:['GDN 状态','循环状态槽位','槽'],
}
const presets = [
  ['轻量','优先留出显存',4096,1],
  ['日常对话','平衡缓存与资源',16384,2],
  ['长程任务','优先扩大 KV',131072,2],
]
const phaseNames={idle:'未启动',starting:'正在启动',ready:'引擎就绪',stopping:'正在停止',error:'启动失败'}
let status={phase:'idle'}, startup={...defaults}, startupLoaded=false, startupDirty=false, startupBusy=false
let snapshot=null, draft={}, draftRevision='', presetName='', poolsKey='', cacheBusy=false, refreshBusy=false, cacheUnavailable=false
let view='runtime', conversation, messages=[], generating=false
let workspace, todos=[], deliverables=[], liveText='', pendingTool, choosingWorkspace=false
const poolElements=new Map()
let refreshGeneration=0

function report(id, error) {
  $(id).textContent=error?String(error.message??error):''
  $(id).hidden=!error
}

function openView(next) {
  view=next
  for(const name of ['chat','runtime'])$(name).hidden=name!==view
  for(const button of document.querySelectorAll('[data-view]')){
    if(button.dataset.view===view)button.setAttribute('aria-current','page')
    else button.removeAttribute('aria-current')
  }
  $('breadcrumb').textContent='工作区 / '+(view==='chat'?'本地会话':'模型与缓存')
  if(view==='chat'&&api)void listConversations().catch(error=>report('chat-error',error))
}

function rangeInput(id,min,max,step,value,onInput) {
  const input=node('input')
  Object.assign(input,{type:'range',id,min,max,step,value})
  input.addEventListener('input',()=>onInput(input.valueAsNumber))
  return input
}

function startupRange(key,label,min,max,step,format=number,onChange) {
  const item=node('div',undefined,'startup-item')
  const title=node('label',label)
  const id='startup-'+key
  title.htmlFor=id
  const value=node('output',format(startup[key]))
  value.htmlFor=id
  title.append(value)
  const slider=rangeInput(id,min,max,step,startup[key],n=>{
    startup[key]=n
    startupDirty=true
    value.textContent=format(n)
    $('startup-note').textContent='有未保存的启动参数'
  })
  if(onChange)slider.addEventListener('change',onChange)
  const bounds=node('div',undefined,'bounds')
  bounds.append(node('span',format(min)),node('span',format(max)))
  item.append(title,slider,bounds)
  $('startup-controls').append(item)
}

function startupChoice(key,title,options) {
  const item=node('div',undefined,'startup-item')
  const label=node('label',title)
  label.htmlFor='startup-'+key
  const select=node('select')
  select.id=label.htmlFor
  for(const [value,text] of options){
    const option=node('option',text)
    option.value=value
    select.append(option)
  }
  select.value=startup[key]
  select.addEventListener('change',()=>{
    startup[key]=select.value
    startupDirty=true
    renderStartup()
    $('startup-note').textContent='有未保存的启动参数'
  })
  item.append(label,select)
  $('startup-controls').append(item)
}

function startupToggle(key,title,disabled=false) {
  const item=node('div',undefined,'startup-item checkbox')
  const label=node('label')
  const input=node('input')
  Object.assign(input,{type:'checkbox',id:'startup-'+key,checked:startup[key],disabled})
  input.addEventListener('change',()=>{
    startup[key]=input.checked
    startupDirty=true
    renderStartup()
    $('startup-note').textContent='有未保存的启动参数'
  })
  label.append(input,document.createTextNode(title))
  item.append(label)
  $('startup-controls').append(item)
}

function renderStartup() {
  const area=$('startup-controls')
  area.replaceChildren()
  const pct=n=>Math.round(n*100)+'%'
  const windowLimit=status.bundled?1000000:Math.min(1000000,startup.modelLimit)
  const fitNativeWindow=event=>{
    if(!status.bundled)startup.context=Math.min(startup.context,startup.modelLimit)
    startup.prefill=Math.min(startup.prefill,startup.context)
    startup.output=Math.min(startup.output,startup.context-257)
    const id=event.target.id
    renderStartup()
    $(id).focus()
  }
  startupRange('context','原生窗口上限',1024,windowLimit,1024,number,fitNativeWindow)
  if(!status.bundled)startupRange('modelLimit','GGUF 已核实的上限',1024,2097152,1024,number,fitNativeWindow)
  startupRange('ratio','显存使用比例',.1,.95,.01,pct)
  startupRange('ramHeadroom','为系统预留 RAM',.5,Math.max(32,startup.ramHeadroom),.5,n=>n+' GiB')
  startupRange('vramHeadroom','显存预留',.5,Math.max(12,startup.vramHeadroom),.5,n=>n+' GiB')
  startupRange('prefill','预填充分块',32,Math.min(startup.context,Math.max(8192,startup.prefill)),32)
  startupRange('output','每轮输出上限',64,Math.min(startup.context-257,Math.max(8192,startup.output)),64)
  startupRange('threads','CPU 线程',1,Math.max(64,startup.threads),1)
  startupChoice('moeStrategy','MoE 专家策略',[['auto','自动'],['offload','GPU 缓存换入'],['fused','常驻显存'],['cpu','CPU'],['hybrid','混合']])
  startupChoice('dtype','KV 精度',[['auto','自动'],['int8_per_token_head','INT8'],['fp8_per_token_head','FP8']])
  area.append(node('h2','SSD 设置','settings-heading'))
  startupToggle('experimentalSsd','启用实验性 SSD')
  if(!startup.experimentalSsd)return
  startupToggle('ssdExpertOffload','SSD 专家读取',startup.moeStrategy!=='offload')
  if(startup.ssdExpertOffload)startupRange('ssdExpertStagingMib','暂存上限',4,32,1,n=>n+' MiB')
  startupToggle('ssdKvCheckpoint','跨重启保存 KV',startup.dtype!=='auto'||startup.activeKv)
  if(startup.ssdKvCheckpoint)startupRange('ssdKvLimitMib','检查点上限',16,1024,16,n=>n+' MiB')
  if(status.bundled)startupToggle('activeKv','活动 KV 写入 SSD',startup.dtype!=='auto'||startup.ssdKvCheckpoint)
  if(status.bundled&&startup.activeKv){
    const location=node('div',undefined,'startup-item is-wide')
    const choose=node('button','选择 SSD 目录','outline')
    choose.type='button'
    choose.onclick=()=>action(()=>api.pickSsd())
    location.append(choose,node('span',' '+(status.ssdDirectory??'使用本地数据目录')))
    area.append(location)
    startupRange('activeKvGpu','显存常驻 KV',0,65536,128)
    startupRange('activeKvRam','RAM 缓存',0,8192,64,n=>n+' MiB')
    startupRange('activeKvDisk','SSD 上限',64,65536,64,n=>n+' MiB')
  }
}

function startupPayload() {
  return {...startup,verified:true,
    modelLimit:status.bundled?Math.max(startup.context,startup.modelLimit):startup.modelLimit,
    ssdExpertOffload:startup.ssdExpertOffload&&startup.moeStrategy==='offload',
    ssdKvCheckpoint:startup.ssdKvCheckpoint&&startup.dtype==='auto',
    activeKv:status.bundled&&startup.activeKv&&startup.dtype==='auto'&&!startup.ssdKvCheckpoint}
}

function setStatus(next) {
  const oldPhase=status.phase
  const firstRuntimeStatus=typeof status.bundled==='undefined'&&typeof next.bundled==='boolean'
  const changeLayout=!startupLoaded||status.bundled!==next.bundled||status.ssdDirectory!==next.ssdDirectory
  status=next
  if(firstRuntimeStatus&&!next.bundled&&!next.engine)$('startup').open=true
  if(!startupDirty&&next.settings&&(!startupLoaded||JSON.stringify(next.settings)!==JSON.stringify(lastStartup))){
    lastStartup=next.settings
    startup={...defaults,...next.settings}
    renderStartup()
  }else if(changeLayout)renderStartup()
  startupLoaded=true
  if(oldPhase!==next.phase&&next.phase!=='ready'){
    snapshot=null;draft={};draftRevision='';poolsKey=''
  }
  const ready=next.phase==='ready'
  $('engine-dot').dataset.ready=String(ready)
  $('rail-status').textContent=phaseNames[next.phase]??'未知状态'
  $('model-name').textContent=next.model??'尚未选择模型'
  $('model-meta').textContent=next.model?(next.bundled?'内置 FreeToken':next.engine??'请选择 FreeToken 程序'):'选择本地 GGUF 文件'
  $('model-status').textContent=phaseNames[next.phase]??'未知状态'
  $('pick-model').disabled=startupBusy||!['idle','error'].includes(next.phase)
  $('pick-engine').hidden=Boolean(next.bundled)
  $('pick-engine').disabled=$('pick-model').disabled
  $('engine-action').textContent=ready?'停止引擎':next.phase==='starting'?'取消启动':next.phase==='stopping'?'正在停止':'启动模型'
  $('engine-action').disabled=startupBusy||next.phase==='stopping'||(!ready&&next.phase!=='starting'&&(!next.model||(!next.bundled&&!next.engine)))
  $('save-startup').disabled=startupBusy||['starting','stopping'].includes(next.phase)||!next.model||(!next.bundled&&!next.engine)
  $('chat-status').textContent=ready?'本地引擎已就绪':'启动模型后可发送消息。'
  $('environment').textContent=next.fixture?'界面验收 · 模拟引擎':'本地运行'
  if(next.detail)report('runtime-error',next.detail)
  syncChat()
  if(!ready)renderCache()
}
let lastStartup

async function action(run,{save=false}={}) {
  if(!api||startupBusy)return
  startupBusy=true
  setStatus(status)
  report('runtime-error',null)
  try{
    const next=await run()
    if(save){
      startupDirty=false
      $('startup-note').textContent='启动参数已保存'
    }
    setStatus(next)
  }catch(error){report('runtime-error',error)}
  finally{startupBusy=false;setStatus(status)}
}

const floor = p => p.adjustable?Math.ceil(p.min/p.step)*p.step:p.value
const ceiling = p => p.adjustable?Math.floor(p.max/p.step)*p.step:p.value
const poolBytes = (name,p,changes) => p.resident_bytes??(changes[name]??p.value)*p.unit_bytes
const totalBytes = (snap,changes) => Object.entries(snap.pools).reduce((sum,[name,p])=>sum+poolBytes(name,p,changes),0)

function presetValues(snap,[, ,kv,expert]) {
  const values={}
  const names=['kv_tokens','moe_experts']
  for(const name of names)if(snap.pools[name]?.adjustable)values[name]=floor(snap.pools[name])
  if(totalBytes(snap,values)>snap.budget_bytes)return null
  for(const name of names){
    const p=snap.pools[name]
    if(!p?.adjustable)continue
    const target=name==='kv_tokens'?Math.min(kv,snap.native_window):floor(p)*expert
    const room=snap.budget_bytes-totalBytes(snap,values)+poolBytes(name,p,values)
    values[name]=Math.max(floor(p),Math.floor(Math.min(ceiling(p),target,room/p.unit_bytes)/p.step)*p.step)
  }
  return Object.fromEntries(Object.entries(values).filter(([name,n])=>n!==snap.pools[name].value))
}

function buildPools(snap){
  poolElements.clear()
  $('pools').replaceChildren()
  for(const [name,p] of Object.entries(snap.pools)){
    if(!p.value&&!p.adjustable)continue
    const [title,hint,unit]=labels[name]??[name,'','']
    const id='pool-'+name
    const section=node('div',undefined,'pool')
    const heading=node('div',undefined,'pool-head')
    const copy=node('div')
    const label=node('label',title)
    label.htmlFor=id
    copy.append(label,node('small',hint))
    const reads=node('div',undefined,'pool-value')
    const output=node('output')
    output.htmlFor=id
    const memory=node('span',undefined,'chip')
    reads.append(output,memory)
    heading.append(copy,reads)
    const input=rangeInput(id,floor(p),ceiling(p),p.step||1,p.value,value=>{
      if(!Object.keys(draft).length)draftRevision=snapshot.revision
      if(value===snapshot.pools[name].value)delete draft[name]
      else draft[name]=value
      presetName=''
      renderCache()
    })
    const bounds=node('div',undefined,'bounds')
    bounds.append(node('span',number(floor(p))),node('span',number(ceiling(p))))
    section.append(heading,input,bounds)
    $('pools').append(section)
    poolElements.set(name,{input,output,memory,unit})
  }
}

function renderResources(snap){
  const target=$('resources')
  target.replaceChildren()
  if(!snap){target.append(node('small','引擎未连接'));return}
  for(const [label,free,total] of [['显存',snap.vram_free_gib,snap.vram_total_gib],['系统内存',snap.ram_free_gib,snap.ram_total_gib]]){
    const block=node('div',undefined,'resource')
    const line=node('div',undefined,'resource-line')
    const used=typeof free==='number'&&typeof total==='number'&&total>0?Math.max(0,total-free):null
    line.append(node('strong',label),node('span',used===null?'—':used.toFixed(1)+' / '+total.toFixed(1)+' GiB'))
    block.append(line)
    if(used!==null){
      const meter=node('progress')
      Object.assign(meter,{max:total,value:used})
      meter.setAttribute('aria-label',label+'使用量')
      block.append(meter)
    }
    target.append(block)
  }
  for(const [label,value] of [['预填充',snap.prefill_tps],['生成',snap.decode_tps],['活跃请求',snap.active_requests]]){
    const line=node('div',undefined,'resource-stat')
    line.append(node('span',label),node('strong',typeof value==='number'?number(value)+(label==='活跃请求'?'':' tok/s'):'—'))
    target.append(line)
  }
}

function renderCache(){
  const snap=snapshot
  $('cache-controls').hidden=!snap
  $('cache-profile').hidden=!snap
  if(!snap){
    $('cache-caption').textContent=cacheUnavailable?'缓存状态暂不可用，正在重试。':'启动模型后读取引擎容量。'
    renderResources(null)
    return
  }
  $('cache-caption').textContent='原生窗口 '+number(snap.native_window)+' tokens · 各池共享显存预算'
  $('cache-profile').textContent=['saved','restored'].includes(snap.profile)?'容量已保存':'引擎分配'
  const geometry=JSON.stringify(snap.pools)
  if(geometry!==poolsKey){poolsKey=geometry;buildPools(snap)}
  const changed=Object.keys(draft).length>0
  const stale=changed&&draftRevision!==snap.revision
  const locked=stale||cacheBusy||cacheUnavailable
  const used=totalBytes(snap,draft)
  const over=used>snap.budget_bytes||!snap.budget_bytes
  for(const [name,elements] of poolElements){
    const p=snap.pools[name]
    const value=draft[name]??p.value
    if(elements.input.valueAsNumber!==value)elements.input.value=String(value)
    elements.input.disabled=locked||!p.adjustable
    elements.output.textContent=number(value)+' '+elements.unit
    elements.memory.textContent=gib(poolBytes(name,p,draft))
  }
  for(const [index,button] of Array.from($('presets').children).entries()){
    const values=presetValues(snap,presets[index])
    button.disabled=locked||!values||!Object.keys(values).length
    button.setAttribute('aria-pressed',String(presetName===presets[index][0]))
  }
  $('cache-cost').textContent=gib(used)+' / '+gib(snap.budget_bytes)
  $('cache-cost').classList.toggle('is-over',over)
  $('cache-reset').disabled=cacheBusy||!changed
  $('cache-apply').disabled=locked||!changed||over||snap.active_requests!==0
  $('cache-apply').textContent=cacheBusy?'正在应用…':'应用缓存'
  $('cache-note').textContent=cacheUnavailable?'遥测中断，重新连接后才能应用。':stale?'引擎配置已改变，请重置草稿。':over?'超过组合显存预算，请调低一个或多个缓存池。':
    snap.active_requests?'当前有活跃请求，空闲后可应用。':snap.reload_to_resize?'活动 SSD KV 的容量在引擎重启后生效。':
    snap.recovered_to_gpu?'SSD 发生读写故障，已切换到显存 KV。':changed?'拖动已更新草稿，点击应用后才修改引擎。':''
  renderResources(snap)
}

function mountPresets(){
  for(const preset of presets){
    const button=node('button')
    button.type='button'
    button.append(node('strong',preset[0]),node('small',preset[1]))
    button.onclick=()=>{
      const values=presetValues(snapshot,preset)
      if(!values)return
      draft=values;draftRevision=snapshot.revision;presetName=preset[0]
      renderCache()
    }
    $('presets').append(button)
  }
}

async function refresh(){
  if(!api||refreshBusy||startupBusy||cacheBusy)return
  refreshBusy=true
  const generation=refreshGeneration
  try{
    const next=await api.status()
    if(generation!==refreshGeneration||startupBusy)return
    setStatus(next)
    if(status.phase==='ready'){
      try{
        const current=await api.cacheStatus()
        if(generation===refreshGeneration&&!cacheBusy&&status.phase==='ready'){
          snapshot=current;cacheUnavailable=false;renderCache()
        }
      }catch{
        if(generation===refreshGeneration){cacheUnavailable=true;renderCache()}
      }
    }
  }catch(error){report('runtime-error',error)}
  finally{refreshBusy=false}
}

async function apply(){
  if(!snapshot||$('cache-apply').disabled)return
  cacheBusy=true
  refreshGeneration++
  renderCache()
  report('runtime-error',null)
  try{
    const result=await api.cacheApply({revision:draftRevision,changes:{...draft}})
    if(result?.applied){
      snapshot={...result.snapshot,profile:result.profile??result.snapshot.profile}
      draft={};draftRevision='';presetName=''
    }
  }catch(error){report('runtime-error',error)}
  finally{cacheBusy=false;renderCache()}
}

function syncChat(){
  $('send-chat').disabled=generating||choosingWorkspace||status.phase!=='ready'
  $('cancel-chat').hidden=!generating
  $('new-chat').disabled=generating||choosingWorkspace
  $('choose-workspace').disabled=generating||choosingWorkspace
}

const toolNames={read:'读取文件',write:'写入文件',edit:'编辑文件',glob:'查找文件',grep:'搜索文本',
  bash:'运行 Bash',pwsh:'运行 PowerShell',todo_write:'更新任务列表',ask_user_question:'向你提问',present:'展示交付文件'}
const toolLabel=name=>toolNames[name]??name

function renderMessages(){
  const list=$('transcript')
  list.replaceChildren()
  if(!messages.length)list.append(node('p','发送消息即可开始本地会话。','notice'))
  const calls=new Map()
  const addText=(role,text)=>{
    if(!text)return
    const block=node('div',undefined,'message '+role)
    block.append(node('small',role==='user'?'你':'本地模型'),node('p',text))
    list.append(block)
  }
  for(const {role,content} of messages){
    if(typeof content==='string'){addText(role,content);continue}
    for(const block of content){
      if(block.type==='text')addText(role,block.text)
      if(block.type==='tool_use')calls.set(block.id,toolLabel(block.name))
      if(block.type==='tool_result'){
        const detail=node('details',undefined,'tool-log')
        detail.append(node('summary',(calls.get(block.tool_use_id)??'工具')+(block.is_error?' · 未完成':' · 已完成')),
          node('pre',block.content))
        list.append(detail)
      }
    }
  }
  addText('assistant',liveText)
  list.scrollTop=list.scrollHeight
}

function renderWorkspace(){
  $('workspace-path').textContent=workspace??'选择目录以启用文件和命令工具'
  const list=$('task-list')
  list.replaceChildren()
  for(const task of todos){
    const status={pending:'待办',in_progress:'进行中',completed:'已完成'}[task.status]
    list.append(node('li',status+' · '+task.content))
  }
  $('tasks').hidden=!todos.length
  const files=$('deliverable-list')
  files.replaceChildren()
  for(const {path,description} of deliverables){
    const button=node('button',description||path)
    button.type='button'
    button.title=path
    button.onclick=()=>void api.revealFile(conversation,path).catch(error=>report('chat-error',error))
    files.append(button)
  }
  $('deliverables').hidden=!deliverables.length
}

function loadSession(saved){
  conversation=saved.id
  messages=saved.messages
  workspace=saved.workspace
  todos=saved.todos??[]
  deliverables=saved.deliverables??[]
  liveText=''
  renderWorkspace()
  renderMessages()
}

function toolPrompt(prompt){
  pendingTool=prompt
  $('tool-prompt').hidden=!prompt
  if(!prompt)return
  const question=prompt.kind==='question'
  $('tool-title').textContent=prompt.title
  $('tool-detail').textContent=prompt.detail
  $('tool-answer').value=''
  $('tool-answer').hidden=!question
  $('tool-answer-label').hidden=!question
  $('tool-accept').textContent=question?'发送回答':'允许一次'
  $('tool-deny').textContent=question?'跳过':'拒绝'
  $('tool-accept').disabled=false
  $('tool-deny').disabled=false
}

async function replyToTool(answer){
  if(!pendingTool)return
  $('tool-accept').disabled=true
  $('tool-deny').disabled=true
  try{await api.answerTool(conversation,pendingTool.token,answer)}
  catch(error){
    report('chat-error',error)
    $('tool-accept').disabled=false
    $('tool-deny').disabled=false
  }
}

async function listConversations(){
  const rows=await api.conversations()
  const list=$('conversations')
  list.replaceChildren()
  if(!rows.length)list.append(node('small','暂无本地记录'))
  for(const row of rows){
    const item=node('button',row.title)
    item.type='button';item.disabled=generating||choosingWorkspace
    if(row.id===conversation)item.setAttribute('aria-current','page')
    item.onclick=async()=>{
      try{
        const loaded=await api.loadConversation(row.id)
        if(generating||choosingWorkspace)return
        loadSession(loaded)
        await listConversations()
      }catch(error){report('chat-error',error)}
    }
    list.append(item)
  }
}

async function send(event){
  event.preventDefault()
  const text=$('prompt').value
  if(!text.trim()||$('send-chat').disabled)return
  conversation??=crypto.randomUUID()
  generating=true;syncChat()
  report('chat-error',null)
  $('prompt').value=''
  messages.push({role:'user',content:text})
  renderMessages()
  void listConversations().catch(()=>{})
  try{
    const saved=await api.send(conversation,text)
    if(saved)loadSession(saved)
  }catch(error){
    report('chat-error',error)
    const saved=await api.loadConversation(conversation).catch(()=>null)
    if(saved?.messages.length)loadSession(saved)
    else $('prompt').value=text
  }finally{generating=false;liveText='';toolPrompt(null);report('current-tool',null);renderMessages();syncChat();void listConversations().catch(()=>{})}
}

for(const button of document.querySelectorAll('[data-view]'))button.onclick=()=>openView(button.dataset.view)
$('cache-reset').onclick=()=>{draft={};draftRevision='';presetName='';renderCache()}
$('cache-apply').onclick=()=>void apply()
$('open-data').onclick=()=>api?.openData().catch(error=>report(view==='chat'?'chat-error':'runtime-error',error))
$('pick-model').onclick=()=>void action(()=>api.pick('model'))
$('pick-engine').onclick=()=>void action(()=>api.pick('engine'))
$('engine-action').onclick=()=>{
  refreshGeneration++
  void action(()=>['ready','starting'].includes(status.phase)?api.stop():api.start(startupPayload()),{save:!['ready','starting'].includes(status.phase)})
}
$('startup-form').onsubmit=event=>{
  event.preventDefault();refreshGeneration++
  void action(()=>api.saveStartup(startupPayload()),{save:true})
}
$('new-chat').onclick=()=>{
  if(generating||choosingWorkspace)return
  loadSession({messages:[]})
  $('prompt').focus()
  void listConversations().catch(()=>{})
}
$('choose-workspace').onclick=async()=>{
  if(generating||choosingWorkspace)return
  conversation??=crypto.randomUUID()
  choosingWorkspace=true
  syncChat()
  try{loadSession(await api.selectWorkspace(conversation))}
  catch(error){report('chat-error',error)}
  finally{choosingWorkspace=false;syncChat()}
}
$('tool-response').onsubmit=event=>{
  event.preventDefault()
  if(!pendingTool)return
  const answer=pendingTool.kind==='question'?$('tool-answer').value.trim():true
  if(answer)void replyToTool(answer)
}
$('tool-deny').onclick=()=>void replyToTool(false)
$('composer').onsubmit=send
$('cancel-chat').onclick=()=>void api.cancel().catch(error=>report('chat-error',error))
api?.onDelta(delta=>{
  if(!generating||delta.id!==conversation)return
  if(Object.hasOwn(delta,'prompt'))toolPrompt(delta.prompt)
  if(Object.hasOwn(delta,'tool'))report('current-tool',delta.tool?'工具运行中 · '+toolLabel(delta.tool):null)
  if(delta.todos){todos=delta.todos;renderWorkspace()}
  if(delta.deliverables){deliverables=delta.deliverables;renderWorkspace()}
  if(delta.messages){messages=delta.messages;liveText='';renderMessages()}
  if(delta.text){liveText+=delta.text;renderMessages()}
})
mountPresets()
renderMessages()
setStatus(status)
if(api){void refresh();setInterval(refresh,1800)}
else report('runtime-error','请从远栈桌面程序打开工作区。')
