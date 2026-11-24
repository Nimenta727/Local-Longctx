"""Read-only FreeToken telemetry. Never infer KV occupancy from GPU utilization."""
from dataclasses import dataclass, asdict
from math import isfinite
from .hardware import detect
from .backend import BackendError

def path_value(obj,path):
    if not isinstance(path,list) or not path or len(path)>12:
        raise ValueError("invalid telemetry path")
    for key in path:
        if not isinstance(key,str) or not isinstance(obj,dict) or key not in obj:
            raise ValueError("telemetry schema mismatch")
        obj=obj[key]
    if type(obj) not in (float,int) or not isfinite(obj) or obj<0:
        raise ValueError("invalid telemetry value")
    return obj

@dataclass(frozen=True)
class Metrics:
    ram_free_gib: float
    ram_total_gib: float
    vram_free_gib: float
    vram_total_gib: float
    kv_occupancy: float
    prefill_tokens_per_second: float
    active_requests: int

def sample(backend,config,profile,probe=detect):
    # Profiles are explicit field paths verified against the installed version.
    # No guessed fields or fallback zeros. Endpoint access is read-only.
    if not isinstance(profile,dict) or set(profile)!={"kv_used","kv_capacity","prefill_tps","active_requests"}:
        raise ValueError("a verified telemetry profile is required")
    stats=backend.json("/v1/stats",timeout=5)
    cache=backend.json("/v1/cache/status",timeout=5)
    used=path_value(cache,profile["kv_used"])
    capacity=path_value(cache,profile["kv_capacity"])
    rate=path_value(stats,profile["prefill_tps"])
    active=path_value(stats,profile["active_requests"])
    if not capacity or used>capacity or rate<=0 or int(active)!=active:
        raise ValueError("unusable telemetry; collect measurements after a real prefill")
    hw=probe(config.state_dir)
    gpu=next((x for x in hw.nvidia if x.uuid==backend.decision.gpu_uuid),None)
    if gpu is None or hw.ram_available_gib is None or hw.ram_total_gib is None:
        raise ValueError("selected GPU or host memory telemetry unavailable")
    return Metrics(hw.ram_available_gib,hw.ram_total_gib,gpu.free_gib,gpu.total_gib,
                   used/capacity,rate,int(active))
