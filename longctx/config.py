"""FreeToken settings and estimates / FreeToken 配置与资源估算。"""
from dataclasses import dataclass
from pathlib import Path
import json
import math
import re

GIB=1024**3
MOE_STRATEGIES=("auto","offload","fused","cpu","hybrid")

@dataclass(frozen=True)
class Config:
    freetoken_server: Path
    model: Path
    model_id: str="local-longctx"
    context: int=32768
    model_limit: int=32768
    logical_target: int=1000000
    output_reserve: int=1024
    ubatch: int=512
    threads: int=4
    api_port: int=18080
    backend_port: int=18081
    gateway_port: int=18799
    timeout: int=7200
    state_dir: Path=Path(".local-longctx")
    model_is_moe: bool=False
    freetoken_model_verified: bool=False
    freetoken_min_vram_gib: float=4
    freetoken_memory_ratio: float=.8
    kv_cache_dtype: str="auto"
    kv_tokens: int=0  # zero: native auto sizing
    expert_slots: int=0  # zero: native auto sizing
    attention_layers: int=0
    kv_heads: int=0
    head_dim: int=0
    host_weights_gib: float | None=None
    ram_headroom_gib: float=2
    vram_headroom_gib: float=1
    moe_strategy: str="auto"
    experimental_ssd: bool=False
    ssd_expert_offload: bool=False
    ssd_kv_checkpoint: bool=False
    ssd_expert_staging_mib: int=4
    ssd_kv_limit_mib: int=256
    bundled_engine: bool=False
    ssd_active_kv: bool=False
    ssd_active_kv_ram_mib: int=256
    ssd_active_kv_gpu_tokens: int=1024
    ssd_active_kv_disk_mib: int=4096
    ssd_active_kv_dir: Path | None=None

    @property
    def ssd_active_kv_enabled(self):
        return self.experimental_ssd and self.ssd_active_kv

    @property
    def ssd_experts_enabled(self):
        return self.experimental_ssd and self.ssd_expert_offload

    @property
    def ssd_kv_enabled(self):
        return self.experimental_ssd and self.ssd_kv_checkpoint

    @property
    def mode(self):
        return "native-experimental"

    def validate(self):
        for k in ("context","model_limit","logical_target","output_reserve","ubatch",
                  "threads","api_port","backend_port","gateway_port","timeout",
                  "attention_layers","kv_heads","head_dim","kv_tokens","expert_slots",
                  "ssd_expert_staging_mib","ssd_kv_limit_mib","ssd_active_kv_ram_mib",
                  "ssd_active_kv_gpu_tokens","ssd_active_kv_disk_mib"):
            if type(getattr(self,k)) is not int:
                raise ValueError(k+" must be an integer")
        if not 0<=self.kv_tokens<=2097152 or not 0<=self.expert_slots<=1000000:
            raise ValueError("invalid cache capacity")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}",self.model_id):
            raise ValueError("invalid model ID")
        if not 0<self.output_reserve<self.context-256 or not self.context<=self.model_limit<=2097152:
            raise ValueError("invalid context budget")
        if not self.context<=self.logical_target<=10000000:
            raise ValueError("invalid logical target")
        if not 1<=self.ubatch<=self.context or not 1<=self.threads<=1024:
            raise ValueError("invalid chunk or threads")
        ports=(self.api_port,self.backend_port,self.gateway_port)
        if len(set(ports))!=3 or any(not 1024<=p<=65535 for p in ports):
            raise ValueError("invalid ports")
        if not 1<=self.timeout<=86400 or min(self.attention_layers,self.kv_heads,self.head_dim)<0:
            raise ValueError("invalid geometry or timeout")
        if self.moe_strategy not in MOE_STRATEGIES:
            raise ValueError("unsupported MoE strategy")
        if self.kv_cache_dtype not in ("auto","fp8_per_token_head","int8_per_token_head"):
            raise ValueError("unsupported native KV dtype")
        for k in ("model_is_moe","freetoken_model_verified","experimental_ssd","ssd_expert_offload","ssd_kv_checkpoint","bundled_engine","ssd_active_kv"):
            if type(getattr(self,k)) is not bool:
                raise ValueError(k+" must be a boolean")
        if not 4<=self.ssd_expert_staging_mib<=32 or not 16<=self.ssd_kv_limit_mib<=1024:
            raise ValueError("invalid SSD budget")
        if self.ssd_experts_enabled and self.moe_strategy!="offload":
            raise ValueError("SSD expert offload requires MoE strategy offload")
        if self.ssd_kv_enabled and self.kv_cache_dtype!="auto":
            raise ValueError("SSD KV checkpoint requires Auto KV precision")
        if not (0 <= self.ssd_active_kv_ram_mib <= 8192 and 0 <= self.ssd_active_kv_gpu_tokens <= 65536
                and 64 <= self.ssd_active_kv_disk_mib <= 65536):
            raise ValueError("invalid active KV budget")
        if self.ssd_active_kv_enabled and (not self.bundled_engine or self.kv_cache_dtype!="auto" or self.ssd_kv_enabled):
            raise ValueError("Active SSD KV requires bundled engine, Auto KV precision, and disabled prefix checkpoints")
        if self.ssd_active_kv_enabled and self.ssd_active_kv_dir is not None and not self.ssd_active_kv_dir.is_dir():
            raise ValueError("Active SSD KV directory does not exist")
        for k in ("freetoken_min_vram_gib","freetoken_memory_ratio","ram_headroom_gib","vram_headroom_gib","host_weights_gib"):
            v=getattr(self,k)
            if k=="host_weights_gib" and v is None:
                continue
            if type(v) not in (int,float) or not math.isfinite(v) or v<=0:
                raise ValueError("invalid "+k)
        if not .1<=self.freetoken_memory_ratio<=.95:
            raise ValueError("invalid memory ratio")
        if not self.freetoken_server.is_file() or not self.model.is_file() or self.model.suffix.lower()!=".gguf":
            raise ValueError("select trusted local ft executable and MoE GGUF")
        with self.model.open("rb") as fp:
            if fp.read(4)!=b"GGUF":
                raise ValueError("invalid GGUF magic")
        return self

    @classmethod
    def load(cls,path):
        path=Path(path).resolve()
        data=json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data,dict):
            raise ValueError("configuration must be an object")
        for k in ("freetoken_server","model","state_dir","ssd_active_kv_dir"):
            if data.get(k) is not None:
                data[k]=(path.parent/data[k]).resolve()
        data.setdefault("state_dir",path.parent/".local-longctx")
        return cls(**data).validate()

def host_weight_estimate_gib(c):
    if c.ssd_experts_enabled:
        from .ssd_experts import SSDExpertReader

        with SSDExpertReader(c.model, c.ssd_expert_staging_mib*2**20) as reader:
            estimate=reader.host_weight_estimate_bytes/GIB
    else:
        estimate=c.model.stat().st_size/GIB
    return c.host_weights_gib if c.host_weights_gib is not None else estimate


def memory_plan(c):
    known=all((c.attention_layers,c.kv_heads,c.head_dim))
    per_token=2*c.attention_layers*c.kv_heads*(2*c.head_dim if c.kv_cache_dtype=="auto" else c.head_dim+4)
    return {"engine":"freetoken","native_window":c.context,"logical_target":c.logical_target,
            "output_reserve":c.output_reserve,"weight_file_gib":c.model.stat().st_size/GIB,
            "attention_kv_estimate_gib":per_token*(c.kv_tokens or c.context)/GIB if known else None,
            "kv_dtype":c.kv_cache_dtype,"requested_kv_tokens":c.kv_tokens or None,
            "expert_slots":c.expert_slots or None,
            "experimental_ssd":c.experimental_ssd,
            "ssd_expert_offload":c.ssd_experts_enabled,"ssd_kv_checkpoint":c.ssd_kv_enabled,
            "host_weight_estimate_gib":host_weight_estimate_gib(c),
            "warning":"GQA estimate only; auto assumes 16-bit. Excludes shards, recurrent state, workspace, MLA/SWA and experts. Logical target is not a native window."}
