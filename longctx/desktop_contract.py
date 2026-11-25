"""Desktop capability contract / 桌面功能与参数预检契约。"""

from .config import MOE_STRATEGIES

TARGET=1_000_000
MODES=("exact","compressed","adaptive","virtual")
SETTINGS=("context","output_reserve","ubatch","threads","freetoken_memory_ratio","kv_cache_dtype","kv_tokens","expert_slots",
          "freetoken_min_vram_gib","ram_headroom_gib","vram_headroom_gib","host_weights_gib","moe_strategy",
          "experimental_ssd","ssd_expert_offload","ssd_kv_checkpoint","ssd_expert_staging_mib","ssd_kv_limit_mib",
          "ssd_active_kv","ssd_active_kv_ram_mib","ssd_active_kv_gpu_tokens","ssd_active_kv_disk_mib")

def describe(c):
    return {
        "contract_version":1,
        "product":"FarStack",
        "engine":"freetoken",
        "context":{"product_target":TARGET,"configured_native_window":c.context,
                   "declared_model_limit":c.model_limit,"output_reserve":c.output_reserve,
                   "native_million_verified":False,"unlimited_history_verified":False,
                   "native_window_status":"engine-confirmed ceiling; admission also checks live KV capacity",
                   "current_mode":c.mode,"logical_target":c.logical_target},
        "capabilities":{
            "text_chat":{"status":"experimental"},
            "native_messages":{"status":"transport_preview_not_end_to_end_verified"},
            "image_input":{"status":"not_integrated"},
            "document_import":{"status":"not_integrated"},
            "web_search":{"status":"not_integrated","enabled":False},
            "workspace_edit":{"status":"not_integrated","enabled":False},
            "managed_compact":{"status":"explicit_preview_commit_rollback"},
            "automatic_compact":{"status":"desktop_budget_projection_experimental"},
            "settings_apply":{"status":"startup_and_native_idle_rebuild_experimental"}
        },
        "memory_controls":{
            "apply_while_idle":["kv_tokens","moe_experts","swa_tokens","mamba_slots"],
            "moe_strategies":list(MOE_STRATEGIES),
            "ssd_kv_offload":c.ssd_active_kv_enabled,
            "experimental_ssd":c.experimental_ssd,
            "ssd_kv_checkpoint":c.ssd_kv_enabled,
            "ssd_expert_offload":c.ssd_experts_enabled,
        },
        "settings":{k:getattr(c,k) for k in SETTINGS},
        "frontend":{"target":"Local-Longctx Studio / Harness","source_status":"pinned_overlay"},
        "notes":["No claim of native million context or unlimited retention.",
                 "Do not enable unsupported actions in a frontend.",
                 "Startup settings require a restart; native pool resize is an experimental idle-only action."]
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
