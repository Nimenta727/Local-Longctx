"""Select only a FreeToken-compatible NVIDIA device; no fallback."""
from dataclasses import dataclass,asdict
from .hardware import detect,GIB

@dataclass(frozen=True)
class Decision:
    engine: str
    gpu_uuid: str
    threads: int
    vram_budget_gib: float
    memory_ratio: float
    prefill_chunk: int
    reason: str

def choose(c,hw):
    if not c.model_is_moe or not c.freetoken_model_verified:
        raise ValueError("verify exact MoE checkpoint and FreeToken version first")
    if hw.os not in ("Linux","Windows"):
        raise ValueError("NVIDIA Linux/Windows research target only")
    gpu=max(hw.nvidia,key=lambda x:x.free_gib,default=None)
    if not gpu or gpu.free_gib<c.freetoken_min_vram_gib:
        raise ValueError("no eligible NVIDIA GPU")
    host=c.host_weights_gib if c.host_weights_gib is not None else c.model.stat().st_size/GIB
    if hw.ram_available_gib is None or hw.ram_available_gib<host+c.ram_headroom_gib:
        raise ValueError("insufficient measured available RAM for conservative host estimate")
    ratio=min(c.freetoken_memory_ratio,(gpu.free_gib-c.vram_headroom_gib)/gpu.free_gib)
    if ratio<.1:
        raise ValueError("insufficient GPU workspace headroom")
    chunk=min(c.ubatch,512 if gpu.free_gib<8 else 1024 if gpu.free_gib<12 else 4096)
    return Decision("freetoken",gpu.uuid,max(1,min(c.threads,hw.threads)),
                    gpu.free_gib*ratio,ratio,chunk,"preflight estimate; native allocation must still succeed")

def report(c):
    hw=detect(c.state_dir)
    result={"hardware":asdict(hw)}
    try:
        result["selection"]=asdict(choose(c,hw))
    except ValueError as exc:
        result["selection"]=None
        result["rejection"]=str(exc)
    return result
