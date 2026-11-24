"""Validated local-only configuration. No arbitrary command-line passthrough."""
from dataclasses import dataclass
from pathlib import Path
import json
import re

CACHE_BYTES = {"f16": 2, "q8_0": 34 / 32, "q4_0": 18 / 32}
GIB = 1024 ** 3

@dataclass(frozen=True)
class Config:
    server: Path
    model: Path
    model_id: str = "local-longctx"
    context: int = 32768
    model_limit: int = 32768
    output_reserve: int = 1024
    gpu_layers: int = 0
    cpu_moe: bool = False
    kv_on_cpu: bool = True
    cache_type: str = "f16"
    batch: int = 512
    ubatch: int = 128
    threads: int = 4
    api_port: int = 18080
    backend_port: int = 18081
    gateway_port: int = 18799
    timeout: int = 7200
    state_dir: Path = Path(".local-longctx")
    attention_layers: int = 0
    kv_heads: int = 0
    head_dim: int = 0
    ram_gib: float = 16
    vram_gib: float = 0

    @property
    def mode(self):
        return "full" if self.cache_type == "f16" else "compressed"

    def validate(self):
        ints = ("context", "model_limit", "output_reserve", "gpu_layers",
                "batch", "ubatch", "threads", "api_port", "backend_port",
                "gateway_port", "timeout", "attention_layers", "kv_heads", "head_dim")
        for key in ints:
            if type(getattr(self, key)) is not int:
                raise ValueError(key + " must be an integer")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", self.model_id):
            raise ValueError("invalid model_id")
        if not (1 <= self.output_reserve and self.output_reserve + 32 < self.context <= self.model_limit <= 2097152):
            raise ValueError("invalid context/output/model limit")
        if not (1 <= self.ubatch <= self.batch <= self.context):
            raise ValueError("invalid batch sizes")
        if not 1 <= self.threads <= 1024 or not 0 <= self.gpu_layers <= 1000:
            raise ValueError("invalid compute settings")
        if self.cache_type not in CACHE_BYTES:
            raise ValueError("unsupported cache type")
        if any(type(x) is not bool for x in (self.cpu_moe, self.kv_on_cpu)):
            raise ValueError("offload settings must be booleans")
        ports = (self.api_port, self.backend_port, self.gateway_port)
        if len(set(ports)) != 3 or any(not 1024 <= p <= 65535 for p in ports):
            raise ValueError("three distinct unprivileged ports required")
        if not 1 <= self.timeout <= 86400:
            raise ValueError("invalid timeout")
        if min(self.attention_layers, self.kv_heads, self.head_dim) < 0:
            raise ValueError("invalid model metadata")
        if not (0 < self.ram_gib <= 100000 and 0 <= self.vram_gib <= 100000):
            raise ValueError("invalid memory budget")
        if not self.model.is_file() or self.model.suffix.lower() != ".gguf":
            raise ValueError("select an existing GGUF model")
        with self.model.open("rb") as f:
            if f.read(4) != b"GGUF":
                raise ValueError("invalid GGUF magic")
        if not self.server.is_file():
            raise ValueError("select an existing llama-server executable")
        return self

    @classmethod
    def load(cls, path):
        path = Path(path).resolve()
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("config must be an object")
        for key in ("server", "model", "state_dir"):
            if key in data:
                data[key] = (path.parent / data[key]).resolve()
        if "state_dir" not in data:
            data["state_dir"] = path.parent / ".local-longctx"
        return cls(**data).validate()

def memory_plan(c):
    # Only the attention KV formula; recurrent state, workspace and allocator
    # overhead are NOT included. GPU weight placement is not inferred.
    weights = c.model.stat().st_size / GIB
    known = all((c.attention_layers, c.kv_heads, c.head_dim))
    kv = (2 * c.attention_layers * c.kv_heads * c.head_dim *
          c.context * CACHE_BYTES[c.cache_type] / GIB) if known else None
    return {
        "mode": c.mode, "context_total": c.context,
        "output_reserve": c.output_reserve,
        "weight_file_gib": round(weights, 3),
        "attention_kv_gib": round(kv, 3) if kv is not None else None,
        "kv_cpu_requested": c.kv_on_cpu,
        "ram_budget_gib": c.ram_gib, "vram_budget_gib": c.vram_gib,
        "cpu_only_baseline_gib": round(weights + kv, 3) if kv is not None else None,
        "warning": "Estimate only; excludes recurrent state, extra GGUF shards, activation, OS and allocator overhead. No device fit guarantee."
    }
