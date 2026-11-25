"""Native cache geometry and approved idle rebuild / 原生缓存预算与空闲重建。"""
import hashlib
import json
from .hardware import detect

POOLS={"kv_tokens":("num_pages","page_size","kv_per_token"),
       "moe_experts":("moe_cache_size",None,"moe_per_expert"),
       "swa_tokens":("num_swa_pages","swa_page_size","swa_per_token"),
       "mamba_slots":("num_mamba_slots",None,"mamba_per_slot")}

def uint(x):
    if type(x) is not int or not 0<=x<=2**53-1:
        raise ValueError("invalid native cache integer")
    return x

def geometry(raw):
    if not isinstance(raw,dict) or raw.get("state")!="serving":
        raise ValueError("native cache not serving")
    g=raw["geometry"]
    budget=uint(g["cache_budget_bytes"])
    pools={}
    for name,(field,unit,cost) in POOLS.items():
        step=uint(g[unit]) if unit else 1
        count=uint(g[field])
        byte_cost=uint(g["unit_bytes"][cost])
        bounds=g["limits"][name]
        lower,upper=uint(bounds["min"]),uint(bounds["max"])
        if step==0 and count:
            raise ValueError("invalid page unit")
        if upper<lower and upper!=0:
            raise ValueError("invalid native limits")
        value=uint(count*step)
        pools[name]={"value":value,"step":step,"min":lower,"max":upper,
                     "unit_bytes":byte_cost,"adjustable":bool(step and upper and byte_cost and budget)}
    identity={"pools":pools,"budget_bytes":budget}
    return dict(identity,revision=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest())

def snapshot(backend,c,probe=detect):
    raw=backend.json("/v1/cache/status",timeout=5)
    stats=backend.json("/v1/stats",timeout=5)
    g=geometry(raw)
    if getattr(c,"ssd_active_kv_enabled",False):
        for pool in g["pools"].values():
            pool["adjustable"]=False
        kv=g["pools"]["kv_tokens"]
        kv["resident_bytes"]=min(kv["value"]+kv["step"],c.ssd_active_kv_gpu_tokens)*kv["unit_bytes"]
        g["reload_to_resize"]=True
    hw=probe(c.state_dir)
    gpu=next((x for x in hw.nvidia if x.uuid==backend.decision.gpu_uuid),None)
    return dict(g,native_window=c.context,output_reserve=c.output_reserve,
                active_requests=uint(stats["requests"]["active"]),
                completed=uint(stats["requests"]["completed"]),
                prefill_tps=stats["throughput"]["prefill_tps"],
                decode_tps=stats["throughput"]["decode_tps"],
                kv_usage=stats.get("kv"),
                ram_total_gib=hw.ram_total_gib,ram_free_gib=hw.ram_available_gib,
                vram_total_gib=gpu.total_gib if gpu else None,
                vram_free_gib=gpu.free_gib if gpu else None)

def plan(g,changes):
    if not isinstance(changes,dict) or not changes or set(changes)-set(POOLS):
        raise ValueError("invalid cache fields")
    args={}
    estimated=0
    for name,(field,unit,cost) in POOLS.items():
        p=g["pools"][name]
        n=uint(changes.get(name,p["value"]))
        if name in changes:
            if not p["adjustable"] or not p["min"]<=n<=p["max"] or n%p["step"]:
                raise ValueError("cache size outside native limits: "+name)
            args[field]=n//p["step"]
        if n and not p["unit_bytes"]:
            raise ValueError("unknown occupied pool cost")
        estimated=uint(estimated+n*p["unit_bytes"])
    if not g["budget_bytes"] or estimated>g["budget_bytes"]:
        raise ValueError("combined pools exceed native cache budget")
    return {"arguments":args,"estimated_bytes":estimated,"budget_bytes":g["budget_bytes"],
            "warning":"Excludes fixed overhead; native engine makes final fit decision"}

def rebuild(backend,c,body):
    if not isinstance(body,dict) or set(body)!={"revision","changes","confirm"} or body["confirm"] is not True:
        raise ValueError("explicit confirmation and current revision required")
    g=snapshot(backend,c)
    if g["revision"]!=body["revision"] or g["active_requests"]:
        raise ValueError("cache configuration changed or engine busy")
    proposed=plan(g,body["changes"])
    result=backend.json("/v1/cache/rebuild",dict(proposed["arguments"],mode="if_idle",timeout=300),timeout=310)
    if result.get("status")!="ok":
        raise ValueError("native rebuild did not succeed")
    return {"applied":True,"snapshot":snapshot(backend,c),"estimate":proposed}
