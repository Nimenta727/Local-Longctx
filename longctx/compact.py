"""ACE: auditable compact decision policy. Never mutates a prompt or KV pool."""
from dataclasses import dataclass
from math import isfinite

@dataclass(frozen=True)
class Snapshot:
    ram_free_gib: float
    ram_total_gib: float
    vram_free_gib: float
    vram_total_gib: float
    context_tokens: int
    context_limit: int
    output_reserve: int
    growth_tokens_per_second: float
    kv_occupancy: float
    history_dependency: float
    prefill_tokens_per_second: float
    compact_seconds: float
    expected_turns: int
    prefix_recompute_tokens: int
    idle: bool=True
    exact_mode: bool=True
    allow_semantic: bool=False
    cache_hit_fraction: float=0
    seconds_since_compact: float=600
    compact_peak_ram_gib: float=0
    compact_peak_vram_gib: float=0

@dataclass(frozen=True)
class Segment:
    id: str
    tokens: int
    importance: float
    access_frequency: float
    dependency: float
    summary_tokens: int
    pinned: bool=False
    recent: bool=False
    role: str="history"

@dataclass(frozen=True)
class Decision:
    action: str
    pressure: float
    seconds_to_limit: float | None
    estimated_saved_tokens: int
    estimated_cost_seconds: float
    estimated_benefit_seconds: float
    candidates: tuple[str,...]
    reasons: tuple[str,...]

def number(x,lo=0,hi=None):
    if type(x) not in (int,float) or not isfinite(x) or x<lo or (hi is not None and x>hi):
        raise ValueError("invalid telemetry")
    return x

def integer(x,lo=0):
    if type(x) is not int or x<lo:
        raise ValueError("invalid token count")
    return x

def evaluate(s,segments):
    segments=list(segments)
    for total,free in ((s.ram_total_gib,s.ram_free_gib),(s.vram_total_gib,s.vram_free_gib)):
        number(total,.001)
        number(free,0,total)
    for x in (s.kv_occupancy,s.history_dependency,s.cache_hit_fraction):
        number(x,0,1)
    for x in (s.context_tokens,s.output_reserve,s.prefix_recompute_tokens,s.expected_turns):
        integer(x)
    integer(s.context_limit,1)
    if s.prefix_recompute_tokens>s.context_tokens or s.output_reserve>=s.context_limit:
        raise ValueError("invalid context budget")
    number(s.growth_tokens_per_second)
    number(s.prefill_tokens_per_second,.001)
    for x in (s.compact_seconds,s.seconds_since_compact,s.compact_peak_ram_gib,s.compact_peak_vram_gib):
        number(x)
    if any(type(x) is not bool for x in (s.idle,s.exact_mode,s.allow_semantic)):
        raise ValueError("invalid mode flag")
    seen=set()
    for item in segments:
        if not isinstance(item.id,str) or not item.id or item.id in seen:
            raise ValueError("invalid segment identity")
        seen.add(item.id)
        integer(item.tokens,1)
        integer(item.summary_tokens)
        if item.summary_tokens>item.tokens:
            raise ValueError("summary exceeds source")
        for x in (item.importance,item.access_frequency,item.dependency):
            number(x,0,1)
        if type(item.pinned) is not bool or type(item.recent) is not bool:
            raise ValueError("invalid segment flags")
    if sum(x.tokens for x in segments)>s.context_tokens:
        raise ValueError("segment tokens exceed prompt")
    used=s.context_tokens+s.output_reserve
    pressure=max(1-s.ram_free_gib/s.ram_total_gib,1-s.vram_free_gib/s.vram_total_gib,
                 s.kv_occupancy,min(1,used/s.context_limit))
    remaining=max(0,s.context_limit-used)
    eta=remaining/s.growth_tokens_per_second if s.growth_tokens_per_second>0 else None
    urgent=pressure>=.95 or remaining==0
    predicted=eta is not None and eta<=max(60,2*s.compact_seconds)
    cost=s.compact_seconds+s.prefix_recompute_tokens/s.prefill_tokens_per_second
    def result(action,*reasons,saved=0,benefit=0,candidates=()):
        return Decision(action,pressure,eta,saved,cost,benefit,tuple(candidates),tuple(reasons))
    if not s.idle:
        return result("defer","active inference; no live mutation")
    if pressure<.8 and not predicted:
        return result("keep","resources and growth forecast within budget")
    if s.exact_mode or not s.allow_semantic:
        return result("pause_or_native_reclaim" if urgent else "native_reclaim_advice",
                      "exact/consent gate: preserve active prompt tokens")
    if s.history_dependency>=.8:
        return result("pause_or_native_reclaim" if urgent else "keep","high historical dependency")
    if s.cache_hit_fraction>=.8 and used<.9*s.context_limit and not predicted and not urgent:
        return result("keep","warm prefix and sufficient context headroom")
    if s.seconds_since_compact<60 and not urgent:
        return result("keep","cooldown")
    if s.compact_peak_ram_gib>s.ram_free_gib or s.compact_peak_vram_gib>s.vram_free_gib:
        return result("pause_or_native_reclaim","compaction workspace will not fit")
    eligible=[x for x in segments if not x.pinned and not x.recent
              and x.role in ("history","tool_result") and x.tokens>x.summary_tokens
              and max(x.importance,x.dependency)<.5 and x.access_frequency<.7]
    eligible.sort(key=lambda x:(.45*x.importance+.2*x.access_frequency+.35*x.dependency,
                                -(x.tokens-x.summary_tokens),x.id))
    target=max(1,used-int(.65*s.context_limit))
    picked=[]
    saved=0
    for x in eligible:
        picked.append(x.id)
        saved+=x.tokens-x.summary_tokens
        if saved>=target:
            break
    benefit=saved/s.prefill_tokens_per_second*s.expected_turns*(1-s.cache_hit_fraction)
    if not picked or saved<target:
        return result("pause_or_native_reclaim" if urgent else "keep","insufficient low-risk history",
                      saved=saved,benefit=benefit)
    if benefit<=1.2*cost and not urgent:
        return result("keep","savings do not amortize compaction and prefix replay",saved=saved,benefit=benefit)
    return result("propose_semantic_compact","pressure or forecast crossed threshold",
                  "archive originals; validate summary, recount and explicitly commit while idle",
                  saved=saved,benefit=benefit,candidates=picked)
