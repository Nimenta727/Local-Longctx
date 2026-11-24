"""Independent admission and prefix identity policy, not tensor migration."""
from dataclasses import dataclass
import hashlib

def check_budget(prompt,output,limit,margin=16):
    if any(type(v) is not int for v in (prompt,output,limit,margin)):
        raise ValueError("invalid token count")
    if min(prompt,margin)<0 or min(output,limit)<1 or prompt+output+margin>limit:
        raise ValueError("context budget exceeded; no automatic truncation")

def digest(tokens):
    h=hashlib.sha256()
    for t in tokens:
        if type(t) is not int or not 0<=t<2**32:
            raise ValueError("invalid token id")
        h.update(t.to_bytes(4,"little"))
    return h.hexdigest()

@dataclass(frozen=True)
class Identity:
    engine: str
    revision: str
    model_hash: str
    tokenizer_hash: str
    template_hash: str
    state_schema: str
    cache_dtype: str
    rope_hash: str
    session: str

@dataclass(frozen=True)
class Checkpoint:
    identity: Identity
    prefix_length: int
    prefix_hash: str

def checkpoint(identity,tokens):
    return Checkpoint(identity,len(tokens),digest(tokens))

def reusable(saved,identity,tokens):
    n=saved.prefix_length
    return saved.identity==identity and 0<=n<=len(tokens) and saved.prefix_hash==digest(tokens[:n])

def tier_policy():
    return {"vram":"engine-owned hot KV, recurrent state and experts",
            "ram":"native host offload, subject to backend support",
            "ssd":"cold weights; opaque verified checkpoints planned",
            "migration":"not implemented",
            "attention":"native kernels first; experimental changes require accuracy gates"}
