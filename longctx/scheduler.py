"""Engine selection before a session; never silently switch live engines."""
from dataclasses import dataclass, asdict
from .hardware import detect, GIB

@dataclass(frozen=True)
class Decision:
    engine: str
    gpu_uuid: str | None
    threads: int
    vram_budget_gib: float | None
    reason: str

def choose(c, hw):
    gpu = max(hw.nvidia,key=lambda g:g.free_gib,default=None)
    eligible = bool(c.freetoken_server and c.freetoken_server.is_file()
                    and c.model_is_moe and c.freetoken_model_verified
                    and hw.os in ("Linux","Windows")
                    and gpu and gpu.free_gib >= c.freetoken_min_vram_gib
                    and hw.ram_available_gib is not None
                    and hw.ram_available_gib >= c.model.stat().st_size/GIB+4)
    threads = min(c.threads,hw.threads)
    if c.engine == "freetoken" and not eligible:
        raise ValueError("FreeToken eligibility failed: check model, executable, NVIDIA and available memory")
    if c.engine != "llama" and eligible:
        return Decision("freetoken",gpu.uuid,threads,gpu.free_gib*c.freetoken_memory_ratio,
                        "user-confirmed MoE compatibility and preliminary resource screen")
    return Decision("llama",None,threads,None,
                    "explicit llama.cpp" if c.engine=="llama" else "FreeToken not eligible before startup")

def report(c):
    hw = detect(c.state_dir)
    return {"hardware":asdict(hw),"selection":asdict(choose(c,hw)),
            "warning":"Eligibility is not a fit guarantee. No live fallback."}
