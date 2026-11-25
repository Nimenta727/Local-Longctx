import { useEffect, useRef, useState } from 'react'
import styles from './ModelsSection.module.css'
import { CachePanel, type CacheBridge } from './LocalCachePanel.tsx'

type Settings = {context:number;modelLimit:number;output:number;threads:number;ratio:number;dtype:string;kvTokens:number;expertSlots:number;prefill:number;moeStrategy:string;minVram:number;vramHeadroom:number;ramHeadroom:number;hostWeights:number|null;experimentalSsd:boolean;ssdExpertOffload:boolean;ssdKvCheckpoint:boolean;ssdExpertStagingMib:number;ssdKvLimitMib:number;activeKv:boolean;activeKvRam:number;activeKvGpu:number;activeKvDisk:number}
type State = { phase: string; model: string | null; engine: string | null; bundled?:boolean; ssdDirectory?:string|null; detail?: string; settings?: Settings; activeSettings?: Settings }
type LocalConnection = {model: string; baseURL: string; key: string; context: number; output: number}
type Bridge = CacheBridge & {
  status(): Promise<State>
  pick(kind: 'model' | 'engine'): Promise<State>
  pickSsd(): Promise<State>
  start(settings: Settings & {verified:boolean}): Promise<State>
  saveStartup(settings: Settings & {verified:boolean}): Promise<State>
  stop(): Promise<State>
  openData(): Promise<void>
  copyKey(): Promise<void>
  connection(): Promise<LocalConnection>
}
export function localLongctxBridge(): Bridge | undefined {
  return (window as Window & { localLongctx?: Bridge }).localLongctx
}
export function LocalLongctxPanel({registerModel}:{registerModel?:(connection:LocalConnection)=>Promise<void>}={}) {
  const bridge = localLongctxBridge()
  const [state, setState] = useState<State>({phase:'idle',model:null,engine:null})
  const [context,setContext] = useState(8192)
  const [limit,setLimit] = useState(32768)
  const [output,setOutput] = useState(1024)
  const [threads,setThreads] = useState(8)
  const [ratio,setRatio] = useState(.8)
  const [dtype,setDtype] = useState('auto')
  const [ssdKvCheckpoint,setSsdKvCheckpoint]=useState(false)
  const [activeKv,setActiveKv]=useState(false)
  const [activeKvRam,setActiveKvRam]=useState(256)
  const [activeKvGpu,setActiveKvGpu]=useState(1024)
  const [activeKvDisk,setActiveKvDisk]=useState(4096)
  const [experimentalSsd,setExperimentalSsd]=useState(false)
  const [ssdKvLimitMib,setSsdKvLimitMib]=useState(256)
  const [kvTokens,setKvTokens]=useState(0)
  const [expertSlots,setExpertSlots]=useState(0)
  const [prefill,setPrefill]=useState(512)
  const [moeStrategy,setMoeStrategy]=useState('auto')
  const [ssdExpertOffload,setSsdExpertOffload]=useState(false)
  const [ssdExpertStagingMib,setSsdExpertStagingMib]=useState(4)
  const [minVram,setMinVram]=useState(4)
  const [vramHeadroom,setVramHeadroom]=useState(1)
  const [ramHeadroom,setRamHeadroom]=useState(2)
  const [hostWeights,setHostWeights]=useState<number|null>(null)
  const [saved,setSaved]=useState(false)
  const [verified,setVerified] = useState(false)
  const [busy,setBusy] = useState(false)
  const [error,setError] = useState('')
  const [copied,setCopied] = useState(false)
  const [registrationError,setRegistrationError]=useState(false)
  const registered=useRef(false)
  useEffect(() => {
    if (!bridge) return
    let live=true, loaded=false
    const refresh=()=>{void bridge.status().then(s=>{
      if(!live)return
      setState(s)
      if(!loaded&&s.settings){
        const x=s.settings
        setContext(x.context);setLimit(x.modelLimit);setOutput(x.output);setThreads(x.threads)
        setRatio(x.ratio);setDtype(x.dtype);setKvTokens(x.kvTokens);setExpertSlots(x.expertSlots);setPrefill(x.prefill)
        setMoeStrategy(x.moeStrategy);setMinVram(x.minVram);setVramHeadroom(x.vramHeadroom)
        setRamHeadroom(x.ramHeadroom);setHostWeights(x.hostWeights);setSsdExpertOffload(x.ssdExpertOffload)
        setSsdKvCheckpoint(x.ssdKvCheckpoint)
        setActiveKv(x.activeKv);setActiveKvRam(x.activeKvRam);setActiveKvGpu(x.activeKvGpu);setActiveKvDisk(x.activeKvDisk)
        setExperimentalSsd(x.experimentalSsd)
        setSsdExpertStagingMib(x.ssdExpertStagingMib);setSsdKvLimitMib(x.ssdKvLimitMib)
      }
      loaded=true
    }).catch(()=>{})}
    refresh()
    const timer=window.setInterval(refresh,1500)
    return ()=>{live=false;window.clearInterval(timer)}
  },[bridge])
  useEffect(()=>{
    if(state.phase!=='ready'){
      registered.current=false
      setRegistrationError(false)
      return
    }
    if(!state.bundled||!registerModel||!bridge||registered.current)return
    registered.current=true
    void bridge.connection().then(registerModel).catch(()=>setRegistrationError(true))
  },[state.phase,state.bundled,bridge,registerModel])
  if(!bridge) return null
  const draftLocked=busy||['starting','stopping'].includes(state.phase)
  const locked=draftLocked||state.phase==='ready'
  const draft={context,modelLimit:limit,output,threads,ratio,dtype,verified:verified||state.bundled===true,kvTokens,expertSlots,prefill,
    moeStrategy,minVram,vramHeadroom,ramHeadroom,hostWeights,experimentalSsd,
    ssdExpertOffload,ssdKvCheckpoint,ssdExpertStagingMib,ssdKvLimitMib,activeKv,activeKvRam,activeKvGpu,activeKvDisk}
  const canSave=!draftLocked&&draft.verified&&!!state.model&&!!state.engine
  const matchesSaved=saved&&state.settings!==undefined&&Object.entries(state.settings)
    .every(([key,value])=>draft[key as keyof Settings]===value)
  const perform=async(action:()=>Promise<State>,save=false)=>{
    setBusy(true);setError('');setSaved(false)
    try{setState(await action());setSaved(save)}catch(e){setError(String(e))}finally{setBusy(false)}
  }
  return <section className={styles['editor']} aria-label="Local-Longctx">
    <h3>远栈 FarStack · 模型与存储</h3>
    <p>逻辑上下文目标 / Logical target: 1,000,000 tokens. 原生窗口仍需验证 / Native window requires validation.</p>
    <button type="button" onClick={()=>{void bridge.openData().catch(e=>setError(String(e)))}}>打开本地数据目录 / Open local data folder</button>
    <p role="status">{state.phase}{state.detail ? ' — '+state.detail : ''}</p>
    {!state.bundled ? <button type="button" disabled={locked} onClick={()=>{setVerified(false);void perform(()=>bridge.pick('engine'))}}>选择可信 FreeToken 程序 / Engine</button> : null}
    <p>{state.engine ?? '未选择 / Not selected'}</p>
    <button type="button" disabled={locked} onClick={()=>{setVerified(false);void perform(()=>bridge.pick('model'))}}>选择 GGUF（可位于 SSD） / Choose GGUF</button>
    <p>{state.model ?? '未选择 / Not selected'}</p>
    <fieldset disabled={draftLocked}>
    <legend>启动参数 / Apply at next start</legend>
    <label>原生窗口 / Native window <input type="number" min={1024} max={1000000} step={1024} disabled={draftLocked} value={context} onChange={e=>setContext(Number(e.target.value))}/></label>
    {!state.bundled ? <label>已核实模型上限 / Model limit <input type="number" min={1024} max={2097152} disabled={draftLocked} value={limit} onChange={e=>{setLimit(Number(e.target.value));setVerified(false)}}/></label> : null}
    <label>输出预留 / Output <input type="number" min={1} disabled={draftLocked} value={output} onChange={e=>setOutput(Number(e.target.value))}/></label>
    <label>CPU 线程 / CPU threads <input type="number" min={1} max={1024} disabled={draftLocked} value={threads} onChange={e=>setThreads(Number(e.target.value))}/></label>
    <label>显存比例 / VRAM ratio <input type="number" min={.1} max={.95} step={.05} disabled={draftLocked} value={ratio} onChange={e=>setRatio(Number(e.target.value))}/></label>
    <label>KV 精度 / KV dtype <select disabled={draftLocked} value={dtype} onChange={e=>{
      setDtype(e.target.value)
      if(e.target.value!=='auto'){setSsdKvCheckpoint(false);setActiveKv(false)}
    }}><option value="auto">Auto</option><option value="int8_per_token_head">INT8</option><option value="fp8_per_token_head">FP8</option></select></label>
    <label>启动 KV 容量 / KV tokens (0=auto) <input type="number" min={0} max={2097152} disabled={draftLocked} value={kvTokens} onChange={e=>setKvTokens(Number(e.target.value))}/></label>
    <label>专家缓存 / Expert slots (0=auto) <input type="number" min={0} max={1000000} disabled={draftLocked} value={expertSlots} onChange={e=>setExpertSlots(Number(e.target.value))}/></label>
    <label>预填充分块 / Prefill chunk <input type="number" min={1} max={context} disabled={draftLocked} value={prefill} onChange={e=>setPrefill(Number(e.target.value))}/></label>
    {!state.bundled ? <label><input type="checkbox" checked={verified} disabled={draftLocked} onChange={e=>setVerified(e.target.checked)}/>已核实模型、引擎来源及兼容性 / Verified compatibility</label> : null}
    <label>专家权重策略 / MoE strategy
      <select value={moeStrategy} onChange={e=>{
        setMoeStrategy(e.target.value)
        if(e.target.value!=='offload')setSsdExpertOffload(false)
      }}>
        <option value="auto">自动 / Auto</option>
        <option value="offload">RAM 专家库 + GPU 缓存 / Offload</option>
        <option value="fused">专家驻留 GPU / Fused</option>
        <option value="cpu">CPU 专家计算 / CPU</option>
        <option value="hybrid">CPU + GPU 专家计算 / Hybrid</option>
      </select>
    </label>
    <label>最低空闲显存 / Minimum free VRAM (GiB)
      <input type="number" min={.1} step={.1} value={minVram} onChange={e=>setMinVram(Number(e.target.value))}/>
    </label>
    <label>显存余量 / VRAM headroom (GiB)
      <input type="number" min={.1} step={.1} value={vramHeadroom} onChange={e=>setVramHeadroom(Number(e.target.value))}/>
    </label>
    <label>内存余量 / RAM headroom (GiB)
      <input type="number" min={.1} step={.1} value={ramHeadroom} onChange={e=>setRamHeadroom(Number(e.target.value))}/>
    </label>
    <label>主机权重估算 / Host weight estimate (GiB)
      <input type="number" min={.1} step={.1}
        placeholder={experimentalSsd&&ssdExpertOffload?'按非专家权重估算 / Non-expert estimate':'按 GGUF 文件大小 / GGUF size'} value={hostWeights??''}
        onChange={e=>setHostWeights(e.target.value===''?null:Number(e.target.value))}/>
    </label>
    <label>
      <input type="checkbox" checked={experimentalSsd} onChange={e=>{
        setExperimentalSsd(e.target.checked)
        if(moeStrategy!=='offload')setSsdExpertOffload(false)
        if(dtype!=='auto'){setSsdKvCheckpoint(false);setActiveKv(false)}
      }} />
      启用实验性 SSD 功能 / Enable experimental SSD
    </label>
    {experimentalSsd ? <fieldset>
      <legend>SSD 参数 / SSD settings</legend>
      <p>需要打过补丁的 FreeToken 和单文件 Qwen3 MoE GGUF。 / Requires patched FreeToken and a single-file Qwen3 MoE GGUF.</p>
      <label>
        <input type="checkbox" checked={ssdExpertOffload} disabled={moeStrategy!=='offload'}
          onChange={e=>setSsdExpertOffload(e.target.checked)} />
        按需读取专家权重（需 Offload） / Stream expert weights (requires Offload)
      </label>
      <label>专家暂存上限 / Expert staging limit ({ssdExpertStagingMib} MiB)
        <input type="range" min={4} max={32} value={ssdExpertStagingMib} disabled={!ssdExpertOffload||moeStrategy!=='offload'}
          onChange={e=>setSsdExpertStagingMib(Number(e.target.value))} />
      </label>
      <label>
        <input type="checkbox" checked={ssdKvCheckpoint} disabled={dtype!=='auto'||activeKv}
          onChange={e=>setSsdKvCheckpoint(e.target.checked)} />
        保存 KV 前缀检查点（需 Auto KV） / Save KV prefix checkpoint (requires Auto KV)
      </label>
      {state.bundled?<label>
        <input type="checkbox" checked={activeKv} disabled={dtype!=='auto'||ssdKvCheckpoint}
          onChange={e=>setActiveKv(e.target.checked)} />推理时将活动 KV 换入 SSD
      </label>:null}
      {state.bundled&&activeKv?<div>
        <button type="button" onClick={()=>void perform(()=>bridge.pickSsd())}>选择活动 KV 的 SSD 目录</button>
        <span>{state.ssdDirectory??'使用本地数据目录'}</span>
        <label>显存常驻 KV {activeKvGpu.toLocaleString()} tokens
          <input type="range" min={0} max={65536} step={128} value={activeKvGpu} onChange={e=>setActiveKvGpu(Number(e.target.value))}/>
        </label>
        <label>RAM 暂存预算 {activeKvRam.toLocaleString()} MiB
          <input type="range" min={0} max={8192} step={64} value={activeKvRam} onChange={e=>setActiveKvRam(Number(e.target.value))}/>
        </label>
        <label>SSD 工作文件上限 {activeKvDisk.toLocaleString()} MiB
          <input type="range" min={64} max={65536} step={64} value={activeKvDisk} onChange={e=>setActiveKvDisk(Number(e.target.value))}/>
        </label>
      </div>:null}
      <label>KV 文件上限 / KV file limit ({ssdKvLimitMib} MiB)
        <input type="range" min={16} max={1024} value={ssdKvLimitMib} disabled={!ssdKvCheckpoint||dtype!=='auto'}
          onChange={e=>setSsdKvLimitMib(Number(e.target.value))} />
      </label>
    </fieldset> : null}
    <button type="button" disabled={!canSave} onClick={()=>void perform(()=>bridge.saveStartup(draft),true)}>
      保存，下次启动生效 / Save for next start
    </button>
    {matchesSaved ? <span role="status">已保存 / Saved</span> : null}
    </fieldset>
    <div><button type="button" disabled={locked||!draft.verified||!state.model||!state.engine} onClick={()=>void perform(()=>bridge.start(draft))}>启动 / Start</button>
    <button type="button" disabled={busy||!['starting','ready'].includes(state.phase)} onClick={()=>void perform(()=>bridge.stop())}>停止 / Stop</button></div>
    {state.phase==='ready' && state.activeSettings ? <p>
      当前引擎 / Running: {state.activeSettings.experimentalSsd&&state.activeSettings.ssdExpertOffload?'SSD experts':state.activeSettings.moeStrategy} · KV {state.activeSettings.dtype} · 配置显存比例 / Configured VRAM ratio {state.activeSettings.ratio}
      {state.activeSettings.experimentalSsd&&state.activeSettings.ssdKvCheckpoint?' · SSD KV checkpoint':''}
    </p> : null}
    {state.phase==='ready' ? <>
      {registrationError&&registerModel?<p role="alert">自动注册本地模型失败。 <button type="button" onClick={()=>{
        setRegistrationError(false)
        void bridge.connection().then(registerModel).catch(()=>setRegistrationError(true))
      }}>重试注册</button></p>:null}
      <button type="button" onClick={()=>{void bridge.copyKey().then(()=>setCopied(true)).catch(e=>setError(String(e)))}}>{copied?'已复制 / Copied':'复制本地 API 密钥 / Copy local API key'}</button>
      <CachePanel bridge={bridge}/>
    </> : null}
    {error ? <p role="alert">{error}</p> : null}
    <p>研发预览：工具协议已接入，本地会话自动管理上下文；工具执行、GPU 与多模态待验证。 / Research preview: Messages transport, automatic local session context management; tools, GPU and multimodal unverified.</p>
  </section>
}
