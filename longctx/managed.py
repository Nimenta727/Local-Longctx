"""ACE managed-session bridge. Ordinary chat completions are never rewritten.

Compaction accepts caller-declared low-risk assistant segments. The initial
executor is deterministic extractive compression, not a semantic guarantee.
"""
from dataclasses import asdict
from .compact import Snapshot,Segment,evaluate
from .session_store import Conflict,validate_messages
from .telemetry import sample

def count(backend,messages):
    n=backend.count_prompt(messages)
    if type(n) is not int or n<0:
        raise ValueError("invalid tokenizer response")
    return n

def extract(text,anchors,budget_chars):
    if type(budget_chars) is not int or budget_chars<64 or budget_chars>=len(text):
        raise ValueError("invalid extractive budget")
    if not isinstance(anchors,list) or not all(isinstance(a,str) and a and a in text for a in anchors):
        raise ValueError("protected literal missing in source")
    # Retain whole source lines where possible, not generated facts.
    lines=text.splitlines()
    selected=set()
    for a in anchors:
        hits=[i for i,line in enumerate(lines) if a in line]
        if not hits:
            raise ValueError("multiline anchor not supported")
        selected.add(hits[0])
    marker="[ACE extract; original retained in local revision archive]"
    def render(indices):
        return marker+"\n"+"\n".join(lines[i] for i in sorted(indices))
    if len(render(selected))>budget_chars:
        raise ValueError("protected lines exceed budget")
    # Alternate beginning/end while staying inside budget.
    for j in range((len(lines)+1)//2):
        for i in (j,len(lines)-1-j):
            trial=selected|{i}
            if len(render(trial))<=budget_chars:
                selected=trial
    result=render(selected)
    if not selected or any(a not in result for a in anchors) or len(result)>=len(text):
        raise ValueError("no valid shorter extract")
    return result

def compact_session(store,backend,c,body,sampler=sample):
    sid=body["session"]
    original=store.read(sid)
    if original["revision"]!=body["expected_revision"] or original["sha256"]!=body["expected_sha"]:
        raise Conflict("stale revision")
    messages=original["messages"]
    if not original["allow_semantic"]:
        return {"action":"keep","reason":"semantic compaction not authorized"}
    if type(body.get("commit",False)) is not bool:
        raise ValueError("commit must be boolean")
    metrics=sampler(backend,c,body["telemetry_profile"])
    if metrics.active_requests:
        return {"action":"defer","reason":"backend has active requests"}
    n=count(backend,messages)
    supplied=body["estimates"]
    required={"growth_tokens_per_second","history_dependency","compact_seconds","expected_turns",
              "prefix_recompute_tokens","cache_hit_fraction","seconds_since_compact",
              "compact_peak_ram_gib","compact_peak_vram_gib"}
    if not isinstance(supplied,dict) or set(supplied)!=required:
        raise ValueError("explicit task and cost estimates required")
    # Candidate metadata is advisory, never inferred from arbitrary text.
    replacements={}
    segments=[]
    for item in body["segments"]:
        i=item["index"]
        if type(i) is not int or not 0<=i<len(messages) or i in replacements:
            raise ValueError("invalid or repeated message index")
        # Never touch system/user messages or last four messages.
        if messages[i]["role"]!="assistant" or i>=len(messages)-4 or item.get("pinned",True) is not False:
            continue
        text=messages[i]["content"]
        replacement=extract(text,item["anchors"],item["budget_chars"])
        # Marginal whole-template token counts; not character ratios.
        altered=[dict(m) for m in messages]
        altered[i]["content"]=replacement
        saved=n-count(backend,altered)
        if saved<=0:
            continue
        replacements[i]=replacement
        segments.append(Segment(str(i),saved,item["importance"],item["access_frequency"],
                                item["dependency"],0,False,False,"history"))
    snapshot=Snapshot(ram_free_gib=metrics.ram_free_gib,ram_total_gib=metrics.ram_total_gib,
                      vram_free_gib=metrics.vram_free_gib,vram_total_gib=metrics.vram_total_gib,
                      context_tokens=n,context_limit=c.context,output_reserve=c.output_reserve,
                      kv_occupancy=metrics.kv_occupancy,prefill_tokens_per_second=metrics.prefill_tokens_per_second,
                      idle=True,exact_mode=False,allow_semantic=True,**supplied)
    decision=evaluate(snapshot,segments)
    report={"decision":asdict(decision),"metrics":asdict(metrics),"revision":original["revision"],
            "before_tokens":n,"committed":False,"quality":"extractive; literal anchors only; semantic equivalence not established"}
    if decision.action!="propose_semantic_compact":
        return report
    new=[dict(m) for m in messages]
    for sid_index in decision.candidates:
        i=int(sid_index)
        new[i]["content"]=replacements[i]
    validate_messages(new)
    after=count(backend,new)
    if after>=n or after+c.output_reserve+256>c.context:
        raise ValueError("compacted prompt failed whole-template budget")
    if n-after<max(1,n+c.output_reserve-int(.65*c.context)):
        raise ValueError("compaction failed low-water target")
    report.update({"after_tokens":after,"saved_tokens":n-after,"preview_messages":new})
    if body.get("commit",False):
        # Check immediately before commit. Gateway holds its shared inference lock.
        if sampler(backend,c,body["telemetry_profile"]).active_requests:
            raise Conflict("backend became busy")
        saved=store.commit(original["session"],original["revision"],original["sha256"],new,"compact")
        report.update({"committed":True,"revision":saved["revision"],"sha256":saved["sha256"]})
    return report

def dispatch(store,backend,c,path,body):
    if not isinstance(body,dict):
        raise ValueError("JSON object required")
    if path=="/local/session/create":
        return store.create(body["session"],body["messages"],body.get("allow_semantic",False))
    if path=="/local/session/read":
        return store.read(body["session"],body.get("revision"))
    if path=="/local/session/append":
        old=store.read(body["session"])
        extra=validate_messages(body["messages"])
        return store.commit(body["session"],body["expected_revision"],body["expected_sha"],
                            old["messages"]+extra,"append")
    if path=="/local/session/rollback":
        return store.rollback(body["session"],body["expected_revision"],body["expected_sha"],body["target_revision"])
    if path=="/local/session/compact":
        return compact_session(store,backend,c,body)
    raise ValueError("unknown managed route")
