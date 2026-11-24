"""GUI-facing capability and configuration preview, not a desktop implementation."""
from dataclasses import dataclass

TARGET=1_000_000
MODES=("exact","compressed","adaptive","virtual")
SETTINGS=("context","output_reserve","ubatch","threads","freetoken_memory_ratio","kv_cache_dtype","kv_tokens","expert_slots")

def describe(c):
    return {
        "contract_version":1,
        "product":"Local-Longctx",
        "engine":"freetoken",
        "context":{"product_target":TARGET,"configured_native_window":c.context,
                   "declared_model_limit":c.model_limit,"output_reserve":c.output_reserve,
                   "native_million_verified":False,"unlimited_history_verified":False,
                   "native_window_status":"configured; not independently benchmarked",
                   "current_mode":c.mode,"logical_target":c.logical_target},
        "capabilities":{
            "text_chat":{"status":"experimental"},
            "image_input":{"status":"not_integrated"},
            "document_import":{"status":"not_integrated"},
            "web_search":{"status":"not_integrated","enabled":False},
            "workspace_edit":{"status":"not_integrated","enabled":False},
            "managed_compact":{"status":"explicit_preview_commit_rollback"},
            "automatic_compact":{"status":"not_integrated"},
            "settings_apply":{"status":"startup_and_native_idle_rebuild_experimental"}
        },
        "settings":{k:getattr(c,k) for k in SETTINGS},
        "frontend":{"target":"Local-Longctx Studio / Harness","source_status":"pinned_overlay"},
        "notes":["No claim of native million context or unlimited retention.",
                 "Do not enable unsupported actions in a frontend.",
                 "All inference settings changes require an idle supervised restart."]
    }

def preview(c,body):
    from dataclasses import replace
    from .config import memory_plan
    if not isinstance(body,dict) or not body or set(body)-set(SETTINGS):
        raise ValueError("only listed inference settings can be previewed")
    candidate=replace(c,**body).validate()
    return {"apply":False,"restart_required":True,
            "settings":{k:getattr(candidate,k) for k in SETTINGS},
            "estimate":memory_plan(candidate),
            "warning":"Validation only; actual allocation and model capability require a real startup."}
