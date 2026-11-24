"""Read-only ACE bridge. Harness owns session mutations and tool pairing.

No content is sent to this endpoint. Unknown relevance and cost are not
fabricated. An observation is not authorization to compact.
"""
from dataclasses import asdict
from .compact import Snapshot,Segment,evaluate,integer
from .telemetry import path_value
from .hardware import detect

ESTIMATES={"growth_tokens_per_second","history_dependency","compact_seconds",
           "expected_turns","prefix_recompute_tokens","cache_hit_fraction",
           "seconds_since_compact","compact_peak_ram_gib","compact_peak_vram_gib"}

def assess(backend,c,body,probe=detect):
    if not isinstance(body,dict) or set(body)-{"context_tokens","range_tokens","estimates","segment","allow_semantic"}:
        raise ValueError("invalid Harness observation")
    n=integer(body["context_tokens"])
    size=integer(body["range_tokens"])
    if size>n:
        raise ValueError("range exceeds context")
    stats=backend.json("/v1/stats",timeout=5)
    used=path_value(stats,["kv","used_pages"])
    total=path_value(stats,["kv","total_pages"])
    rate=path_value(stats,["throughput","prefill_tps"])
    active=path_value(stats,["requests","active"])
    if not total or used>total or int(active)!=active:
        raise ValueError("unverified native stats")
    hw=probe(c.state_dir)
    gpu=next((g for g in hw.nvidia if g.uuid==backend.decision.gpu_uuid),None)
    if gpu is None or hw.ram_available_gib is None or hw.ram_total_gib is None or hw.ram_total_gib<=0 or gpu.total_gib<=0:
        raise ValueError("missing hardware observation")
    metrics={"ram_free_gib":hw.ram_available_gib,"ram_total_gib":hw.ram_total_gib,
             "vram_free_gib":gpu.free_gib,"vram_total_gib":gpu.total_gib,
             "kv_occupancy":used/total,"prefill_tokens_per_second":rate,
             "active_requests":int(active)}
    report={"action":"observe","metrics":metrics,"context_tokens":n,
            "range_tokens":size,"native_window":c.context,"mutation":False}
    if active or rate<=0:
        return dict(report,action="defer",reason="backend busy or no measured prefill rate")
    estimates=body.get("estimates")
    metadata=body.get("segment")
    if body.get("allow_semantic") is not True or not isinstance(estimates,dict) or set(estimates)!=ESTIMATES or not isinstance(metadata,dict):
        return dict(report,reason="explicit task relevance, access and cost estimates plus consent are required")
    if set(metadata)!={"importance","access_frequency","dependency","summary_tokens"}:
        raise ValueError("invalid range metadata")
    if size==0:
        return dict(report,action="keep",reason="no balanced candidate")
    segment=Segment("harness-balanced-range",size,metadata["importance"],metadata["access_frequency"],metadata["dependency"],metadata["summary_tokens"],False,False,"history")
    snap=Snapshot(context_tokens=n,context_limit=c.context,output_reserve=c.output_reserve,
                  idle=True,exact_mode=False,allow_semantic=True,
                  **{k:v for k,v in metrics.items() if k!="active_requests"},**estimates)
    decision=evaluate(snap,[segment])
    return dict(report,action=decision.action,decision=asdict(decision))
