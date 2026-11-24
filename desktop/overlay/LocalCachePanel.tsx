import {useEffect,useState} from 'react'

type Pool={value:number;step:number;min:number;max:number;unit_bytes:number;adjustable:boolean}
type Snapshot={revision:string;pools:Record<string,Pool>;budget_bytes:number;native_window:number;output_reserve:number;active_requests:number;completed:number;prefill_tps:number;decode_tps:number;ram_total_gib:number|null;ram_free_gib:number|null;vram_total_gib:number|null;vram_free_gib:number|null;kv_usage:{used_pages:number;total_pages:number}|null}
export type CacheBridge={cacheStatus():Promise<Snapshot>;cacheApply(draft:{revision:string;changes:Record<string,number>}):Promise<{applied:boolean;snapshot:Snapshot}|null>}
const labels:Record<string,string>={kv_tokens:'KV Cache · tokens',moe_experts:'MoE Expert Cache · slots',swa_tokens:'滑窗 / SWA · tokens',mamba_slots:'GDN state · slots'}
const gib=(n:number)=> (n/1073741824).toFixed(2)
export function CachePanel({bridge}:{bridge:CacheBridge}){
  const [snap,setSnap]=useState<Snapshot|null>(null)
  const [draft,setDraft]=useState<Record<string,number>>({})
  const [revision,setRevision]=useState('')
  const [busy,setBusy]=useState(false)
  const [error,setError]=useState('')
  useEffect(()=>{
    let live=true,running=false
    const refresh=async()=>{
      if(running||busy)return
      running=true
      try{const x=await bridge.cacheStatus();if(live){setSnap(x);setError('')}}
      catch{if(live)setError('原生遥测不可用 / Native telemetry unavailable')}
      finally{running=false}
    }
    void refresh()
    const timer=setInterval(()=>{void refresh()},2000)
    return()=>{live=false;clearInterval(timer)}
  },[bridge,busy])
  if(!snap)return <p>{error||'正在读取缓存 / Loading native cache…'}</p>
  const changed=Object.keys(draft).length>0
  const stale=changed&&revision!==snap.revision
  const total=Object.entries(snap.pools).reduce((n,[name,p])=>n+(draft[name]??p.value)*p.unit_bytes,0)
  const invalid=Object.entries(draft).some(([name,n])=>{const p=snap.pools[name];return !p||!p.adjustable||!Number.isSafeInteger(n)||n<p.min||n>p.max||n%p.step!==0})
  const edit=(name:string,n:number)=>{if(!changed)setRevision(snap.revision);setDraft(x=>({...x,[name]:n}))}
  const preset=(agent:boolean)=>{
    const p=snap.pools.kv_tokens
    if(!p?.adjustable)return
    const target=Math.min(p.max,agent?Math.min(snap.native_window,131072):16384)
    const rounded=Math.max(Math.ceil(p.min/p.step)*p.step,Math.floor(target/p.step)*p.step)
    setRevision(snap.revision);setDraft({kv_tokens:rounded})
  }
  const apply=async()=>{
    setBusy(true);setError('')
    try{const r=await bridge.cacheApply({revision,changes:draft});if(r?.applied){setSnap(r.snapshot);setDraft({})}}
    catch(e){setError(String(e))}
    finally{setBusy(false)}
  }
  return <section aria-label="Native cache settings">
    <h3>Cache 配置 / Native pools</h3>
    <p>模型窗口 / Model window {snap.native_window.toLocaleString()} · KV capacity {snap.pools.kv_tokens?.value.toLocaleString()} · 活跃请求 / Active {snap.active_requests}</p>
    <div><button type="button" disabled={busy} onClick={()=>preset(false)}>Chat 16K</button> <button type="button" disabled={busy} onClick={()=>preset(true)}>Agent ≤128K</button></div>
    {Object.entries(snap.pools).filter(([,p])=>p.value>0||p.adjustable).map(([name,p])=>{
      const n=draft[name]??p.value
      return <div key={name}><label>{labels[name]??name}: {n.toLocaleString()} · {gib(n*p.unit_bytes)} GiB
        <input type="range" min={Math.ceil(p.min/(p.step||1))*(p.step||1)} max={Math.floor(p.max/(p.step||1))*(p.step||1)} step={p.step||1} value={n} disabled={busy||!p.adjustable||stale} onChange={e=>edit(name,Number(e.target.value))}/>
        <input type="number" value={n} step={p.step||1} disabled={busy||!p.adjustable||stale} onChange={e=>edit(name,Number(e.target.value))}/>
      </label></div>
    })}
    <p>预计缓存 / Estimated cache {gib(total)} / {gib(snap.budget_bytes)} GiB （实际以引擎为准 / native final fit may differ）</p>
    <p>RAM {snap.ram_free_gib===null?'—':snap.ram_free_gib.toFixed(2)} / {snap.ram_total_gib??'—'} GiB free · VRAM {snap.vram_free_gib===null?'—':snap.vram_free_gib.toFixed(2)} / {snap.vram_total_gib??'—'} GiB free</p>
    <p>Prefill {snap.prefill_tps} tok/s · Decode {snap.decode_tps} tok/s · Completed {snap.completed} · KV {snap.kv_usage?Math.round(100*snap.kv_usage.used_pages/Math.max(1,snap.kv_usage.total_pages))+'%':'—'}</p>
    <button type="button" disabled={busy||!changed} onClick={()=>setDraft({})}>重置 / Reset</button>
    <button type="button" disabled={busy||!changed||invalid||stale||!!error||snap.active_requests!==0||!snap.budget_bytes||total>snap.budget_bytes} onClick={()=>void apply()}>应用（空闲） / Apply idle</button>
    {stale?<p>缓存已变化，请重置。 / Cache changed; reset and re-plan.</p>:null}{error?<p role="alert">{error}</p>:null}
    <p>实时调整为实验功能，重启不保留；可能使前缀缓存失效，不能扩大模型窗口。 / Experimental, not persisted; may invalidate prefixes and cannot extend the model window.</p>
  </section>
}
