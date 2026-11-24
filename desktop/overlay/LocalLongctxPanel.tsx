import { useEffect, useState } from 'react'
import styles from './ModelsSection.module.css'
import { CachePanel, type CacheBridge } from './LocalCachePanel.tsx'

type Settings = {context:number;modelLimit:number;output:number;threads:number;ratio:number;dtype:string;kvTokens:number;expertSlots:number;prefill:number}
type State = { phase: string; model: string | null; engine: string | null; detail?: string; settings?: Settings }
type Bridge = CacheBridge & {
  status(): Promise<State>
  pick(kind: 'model' | 'engine'): Promise<State>
  start(settings: {context: number; modelLimit: number; output: number; threads: number; ratio: number; dtype: string; verified: boolean; kvTokens:number; expertSlots:number; prefill:number}): Promise<State>
  stop(): Promise<State>
  openData(): Promise<void>
  copyKey(): Promise<void>
  connection(): Promise<{model: string; baseURL: string; key: string; context: number; output: number}>
}
export function localLongctxBridge(): Bridge | undefined {
  return (window as Window & { localLongctx?: Bridge }).localLongctx
}
export function LocalLongctxPanel() {
  const bridge = localLongctxBridge()
  const [state, setState] = useState<State>({phase:'idle',model:null,engine:null})
  const [context,setContext] = useState(8192)
  const [limit,setLimit] = useState(32768)
  const [output,setOutput] = useState(1024)
  const [threads,setThreads] = useState(8)
  const [ratio,setRatio] = useState(.8)
  const [dtype,setDtype] = useState('auto')
  const [kvTokens,setKvTokens]=useState(0)
  const [expertSlots,setExpertSlots]=useState(0)
  const [prefill,setPrefill]=useState(512)
  const [verified,setVerified] = useState(false)
  const [busy,setBusy] = useState(false)
  const [error,setError] = useState('')
  const [copied,setCopied] = useState(false)
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
      }
      loaded=true
    }).catch(()=>{})}
    refresh()
    const timer=window.setInterval(refresh,1500)
    return ()=>{live=false;window.clearInterval(timer)}
  },[bridge])
  if(!bridge) return null
  const locked=busy||['starting','ready','stopping'].includes(state.phase)
  const perform=async(action:()=>Promise<State>)=>{
    setBusy(true);setError('')
    try{setState(await action())}catch(e){setError(String(e))}finally{setBusy(false)}
  }
  return <section className={styles['editor']} aria-label="Local-Longctx">
    <h3>Local-Longctx · 本地 MoE 模型</h3>
    <p>逻辑上下文目标 / Logical target: 1,000,000 tokens. 原生窗口仍需验证 / Native window requires validation.</p>
    <button type="button" onClick={()=>{void bridge.openData().catch(e=>setError(String(e)))}}>打开本地数据目录 / Open local data folder</button>
    <p role="status">{state.phase}{state.detail ? ' — '+state.detail : ''}</p>
    <button type="button" disabled={locked} onClick={()=>{setVerified(false);void perform(()=>bridge.pick('engine'))}}>选择可信 FreeToken 程序 / Engine</button>
    <p>{state.engine ?? '未选择 / Not selected'}</p>
    <button type="button" disabled={locked} onClick={()=>{setVerified(false);void perform(()=>bridge.pick('model'))}}>导入 GGUF / Model</button>
    <p>{state.model ?? '未选择 / Not selected'}</p>
    <label>原生窗口 / Native window <input type="number" min={1024} max={1000000} step={1024} disabled={locked} value={context} onChange={e=>setContext(Number(e.target.value))}/></label>
    <label>已核实模型上限 / Model limit <input type="number" min={1024} max={2097152} disabled={locked} value={limit} onChange={e=>{setLimit(Number(e.target.value));setVerified(false)}}/></label>
    <label>输出预留 / Output <input type="number" min={1} disabled={locked} value={output} onChange={e=>setOutput(Number(e.target.value))}/></label>
    <label>CPU 线程 / CPU threads <input type="number" min={1} max={1024} disabled={locked} value={threads} onChange={e=>setThreads(Number(e.target.value))}/></label>
    <label>显存比例 / VRAM ratio <input type="number" min={.1} max={.95} step={.05} disabled={locked} value={ratio} onChange={e=>setRatio(Number(e.target.value))}/></label>
    <label>KV 精度 / KV dtype <select disabled={locked} value={dtype} onChange={e=>setDtype(e.target.value)}><option value="auto">Auto</option><option value="int8_per_token_head">INT8</option><option value="fp8_per_token_head">FP8</option></select></label>
    <label>启动 KV 容量 / KV tokens (0=auto) <input type="number" min={0} max={2097152} disabled={locked} value={kvTokens} onChange={e=>setKvTokens(Number(e.target.value))}/></label>
    <label>专家缓存 / Expert slots (0=auto) <input type="number" min={0} max={1000000} disabled={locked} value={expertSlots} onChange={e=>setExpertSlots(Number(e.target.value))}/></label>
    <label>预填充分块 / Prefill chunk <input type="number" min={1} max={context} disabled={locked} value={prefill} onChange={e=>setPrefill(Number(e.target.value))}/></label>
    <label><input type="checkbox" checked={verified} disabled={locked} onChange={e=>setVerified(e.target.checked)}/>已核实模型、引擎来源及兼容性 / Verified compatibility</label>
    <div><button type="button" disabled={locked||!verified||!state.model||!state.engine} onClick={()=>void perform(()=>bridge.start({context,modelLimit:limit,output,threads,ratio,dtype,verified,kvTokens,expertSlots,prefill}))}>启动 / Start</button>
    <button type="button" disabled={busy||!['starting','ready'].includes(state.phase)} onClick={()=>void perform(()=>bridge.stop())}>停止 / Stop</button></div>
    {state.phase==='ready' ? <p>在下方添加自定义模型供应商，使用 Local-Longctx 预设。 / Add the Local-Longctx custom provider below.</p> : null}
    {state.phase==='ready' ? <>
      <button type="button" onClick={()=>{void bridge.copyKey().then(()=>setCopied(true)).catch(e=>setError(String(e)))}}>{copied?'已复制 / Copied':'复制本地 API 密钥 / Copy local API key'}</button>
      <CachePanel bridge={bridge}/>
    </> : null}
    {error ? <p role="alert">{error}</p> : null}
    <p>研发预览：工具协议已接入，本地会话自动管理上下文；工具执行、GPU 与多模态待验证。 / Research preview: Messages transport, automatic local session context management; tools, GPU and multimodal unverified.</p>
  </section>
}
