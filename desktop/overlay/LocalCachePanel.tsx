import {useEffect,useState} from 'react'
import styles from './LocalCachePanel.module.css'

type Pool={value:number;step:number;min:number;max:number;unit_bytes:number;adjustable:boolean;resident_bytes?:number}
type Snapshot={profile?:string;revision:string;pools:Record<string,Pool>;budget_bytes:number;native_window:number;output_reserve:number;active_requests:number;completed:number;prefill_tps:number;decode_tps:number;ram_total_gib:number|null;ram_free_gib:number|null;vram_total_gib:number|null;vram_free_gib:number|null;kv_usage:{used_pages:number;total_pages:number}|null;reload_to_resize?:boolean;recovered_to_gpu?:boolean}
export type CacheBridge={cacheStatus():Promise<Snapshot>;cacheApply(draft:{revision:string;changes:Record<string,number>}):Promise<{applied:boolean;snapshot:Snapshot;profile?:string}|null>}

const labels = {
  kv_tokens:['KV 缓存','可为注意力保留的 Token','tokens'],
  moe_experts:['MoE 专家缓存','显存中的专家槽位','槽'],
  swa_tokens:['滑窗 KV','滑动窗口层可用的缓存容量','tokens'],
  mamba_slots:['GDN 状态','可保留的循环状态槽位','槽'],
} as const
const presets = [
  {name:'轻量', hint:'为其他应用保留显存', kv:4096, expertFactor:1},
  {name:'日常对话', hint:'兼顾提示复用与显存', kv:16384, expertFactor:2},
  {name:'长程任务', hint:'优先保留更多 KV 缓存', kv:131072, expertFactor:2},
]
const gib=(n:number)=> (n/1073741824).toFixed(2)
const lower=(p:Pool)=> p.adjustable?Math.ceil(p.min/p.step)*p.step:p.value
const upper=(p:Pool)=> p.adjustable?Math.floor(p.max/p.step)*p.step:p.value
const cost=(s:Snapshot,values:Record<string,number>)=>Object.entries(s.pools)
  .reduce((sum,[name,p])=>sum+(p.resident_bytes??(values[name]??p.value)*p.unit_bytes),0)

export function cachePreset(s:Snapshot, preset:typeof presets[number]):Record<string,number> {
  const values:Record<string,number>={}
  for(const name of ['kv_tokens','moe_experts']){
    const p=s.pools[name]
    if(p?.adjustable)values[name]=lower(p)
  }
  if(cost(s,values)>s.budget_bytes)return {}
  for(const name of ['kv_tokens','moe_experts']){
    const p=s.pools[name]
    if(!p?.adjustable)continue
    const target=name==='kv_tokens'?Math.min(preset.kv,s.native_window):lower(p)*preset.expertFactor
    const room=s.budget_bytes-cost(s,values)+values[name]!*p.unit_bytes
    const cap=Math.min(upper(p),target,Math.floor(room/p.unit_bytes))
    values[name]=Math.max(lower(p),Math.floor(cap/p.step)*p.step)
  }
  return Object.fromEntries(Object.entries(values).filter(([name,value])=>value!==s.pools[name]?.value))
}

function Resource({label,free,total}:{label:string;free:number|null;total:number|null}){
  const known=free!==null&&total!==null&&total>0
  const used=known?Math.max(0,total-free):0
  return <div className={styles.resource}>
    <strong>{label}</strong>
    <span>{known?`${used.toFixed(2)} / ${total.toFixed(2)} GiB`:'—'}</span>
    {known?<progress aria-label={label} max={total} value={used}/>:null}
  </div>
}

export function CachePanel({bridge}:{bridge:CacheBridge}){
  const [snap,setSnap]=useState<Snapshot|null>(null)
  const [draft,setDraft]=useState<Record<string,number>>({})
  const [revision,setRevision]=useState('')
  const [busy,setBusy]=useState(false)
  const [error,setError]=useState('')
  const [telemetryError,setTelemetryError]=useState(false)
  useEffect(()=>{
    let live=true,running=false
    const refresh=async()=>{
      if(running||busy)return
      running=true
      try{const x=await bridge.cacheStatus();if(live){setSnap(x);setTelemetryError(false)}}
      catch{if(live)setTelemetryError(true)}
      finally{running=false}
    }
    void refresh()
    const timer=setInterval(()=>{void refresh()},2000)
    return()=>{live=false;clearInterval(timer)}
  },[bridge,busy])
  if(!snap)return <p role="status">{telemetryError?'无法读取引擎缓存':'正在读取引擎缓存…'}</p>

  const changed=Object.keys(draft).length>0
  const stale=changed&&revision!==snap.revision
  const total=cost(snap,draft)
  const invalid=Object.entries(draft).some(([name,n])=>{
    const p=snap.pools[name]
    return !p||!p.adjustable||!Number.isSafeInteger(n)||n<lower(p)||n>upper(p)||n%p.step!==0
  })
  const unavailable=busy||telemetryError||stale
  const applyBlocked=unavailable||!changed||invalid||snap.active_requests!==0||!snap.budget_bytes||total>snap.budget_bytes
  const edit=(name:string,n:number)=>{
    if(!changed)setRevision(snap.revision)
    setError('')
    setDraft(previous=>{
      if(n!==snap.pools[name]?.value)return {...previous,[name]:n}
      const next={...previous}
      delete next[name]
      return next
    })
  }
  const apply=async()=>{
    setBusy(true);setError('')
    try{
      const r=await bridge.cacheApply({revision,changes:draft})
      if(r?.applied){setSnap({...r.snapshot,...r.profile===undefined?{}:{profile:r.profile}});setDraft({})}
    }catch(e){setError(String(e))}
    finally{setBusy(false)}
  }

  return <section className={styles.panel} aria-label="缓存调度">
    <header className={styles.heading}>
      <div><h3>缓存调度</h3><p>原生窗口 {snap.native_window.toLocaleString()} · 活跃请求 {snap.active_requests}</p></div>
      <span>{snap.profile==='saved'||snap.profile==='restored'?'容量已保存':'引擎配置'}</span>
    </header>
    <div className={styles.presets} aria-label="缓存预设">
      {presets.map(preset=>{
        const next=cachePreset(snap,preset)
        return <button key={preset.name} type="button" disabled={unavailable||Object.keys(next).length===0}
          onClick={()=>{setRevision(snap.revision);setDraft(next);setError('')}}>
          <strong>{preset.name}</strong><span>{preset.hint}</span>
        </button>
      })}
    </div>
    {Object.entries(snap.pools).filter(([,p])=>p.value>0||p.adjustable).map(([name,p])=>{
      const [label,hint,unit]=labels[name as keyof typeof labels]??[name,'','']
      const value=draft[name]??p.value
      const id='farstack-cache-'+name
      return <div key={name} className={styles.pool}>
        <div className={styles.poolHeading}>
          <div><label htmlFor={id}>{label}</label>{hint&&<small>{hint}</small>}</div>
          <div><output htmlFor={id}>{value.toLocaleString()} {unit}</output>
            <span className={styles.cost}>{gib(p.resident_bytes??value*p.unit_bytes)} GiB</span></div>
        </div>
        <input id={id} className={styles.slider} type="range" min={lower(p)} max={upper(p)} step={p.step||1}
          value={value} disabled={unavailable||!p.adjustable} onChange={e=>edit(name,Number(e.target.value))}/>
        <div className={styles.bounds}><span>{lower(p).toLocaleString()}</span><span>{upper(p).toLocaleString()}</span></div>
      </div>
    })}
    <footer className={styles.footer}>
      <div><span>预计缓存显存</span><strong aria-live="polite">{gib(total)} / {gib(snap.budget_bytes)} GiB</strong></div>
      <div>
        <button type="button" disabled={busy||!changed} onClick={()=>{setDraft({});setError('')}}>重置</button>
        <button className={styles.primary} type="button" disabled={applyBlocked} onClick={()=>void apply()}>{busy?'正在应用…':'应用'}</button>
      </div>
    </footer>
    {total>snap.budget_bytes?<p role="status">超过组合显存预算，请调低一个缓存池。</p>:null}
    {snap.reload_to_resize?<p role="status">活动 SSD KV 已启用。容量调整在引擎重启后生效。</p>:null}
    {snap.recovered_to_gpu?<p role="status">SSD 读写失败，已用显存 KV 恢复。后续请求会按当前预算处理。</p>:null}
    {snap.active_requests!==0?<p role="status">请求结束后可以应用此配置。</p>:null}
    {stale?<p role="status">引擎容量已变化，请重置后再调整。</p>:null}
    {telemetryError||error?<p role="alert">{error||'无法读取引擎缓存'}</p>:null}
    {snap.profile==='unavailable'?<p role="status">缓存方案未能保存或恢复。</p>:null}
    <div className={styles.resources}>
      <Resource label="显存" free={snap.vram_free_gib} total={snap.vram_total_gib}/>
      <Resource label="内存" free={snap.ram_free_gib} total={snap.ram_total_gib}/>
    </div>
  </section>
}
