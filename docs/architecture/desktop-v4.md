# V4 product direction: unified FreeToken Desktop workbench

## Decision
Replace the previous OpenClaw-first product direction with FreeToken Desktop as preferred UI. Do not remove working legacy launchers until a replacement is verified. FreeToken remains the only MoE execution base; progressively replace control/scheduling/cache orchestration with Local-Longctx ACMA/AHS/ACE, retain verified CUDA expert/model kernels. Never call an external wrapper a completed engine fork.

## Source and licensing gate
The public FreeToken repository (Apache-2.0) contains Python inference engine sources. Its README distributes Desktop separately; its public root and organization listing do not establish access to editable Desktop UI sources or an equivalent redistribution license. FreeToken-Web is a separate distribution website, not assumed to be Desktop. Request the actual UI repository and explicit applicable license before patching/rebranding/repackaging. Do not modify closed binary packages or copy branding. If unavailable, offer the user a separately approved alternative: reuse DeepSeek Harness's open UI, or create an independent UI. No substitution is made in this commit.

DeepSeek Harness is an open plugin architecture. Reuse reviewed pinned tool packages and adapter contracts, not wholesale default configuration. Its web_search uses a provider; official DeepSeek search requires a credential and network access. Use provider-only search with explicit user enablement, optional alternative provider, no cloud inference fallback, no background uploads. Audit default telemetry/session-log behavior before embedding. Do not transmit local history or files for search by default. Secrets in OS credential store, never frontend storage/logs/config exports. Keep untrusted web/tool results as data, not instructions.

Sources (checked 2026-11-24):
- https://github.com/FlashML-org/FreeToken
- https://github.com/FlashML-org
- https://github.com/deepseek-ai/deepseek-harness
- https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/tool-catalog.md
- https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/web/web-search-deepseek/README.md
- https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/web/web-deepseek-api/README.md
- https://github.com/FlashML-org/FreeToken/blob/main/docs/models.md
- https://github.com/FlashML-org/FreeToken/blob/main/docs/cli.md

## Target composition
Desktop renderer -> trusted local IPC / supervised gateway -> agent loop -> model adapter -> Local-Longctx ACMA/AHS/ACE -> FreeToken execution kernels.
Agent tools -> reviewed DeepSeek Harness web + filesystem plugins -> policy/approval broker -> search provider or user-selected workspace.
Renderer must not access unrestricted local filesystem, spawn shell or hold backend/provider tokens. No remote HTTP binding. Use actual native IPC for desktop; the current loopback API rejects browser Origin headers deliberately.

## GUI-only operations (target)
- Model Library: discover/import verified local model and optional vision encoder; choose GPU, resource caps, model window, output budget, KV format, native/approximate mode.
- Chat: streamed output, stop, attachments, citations, tool cards, diff previews, context meter and history restore.
- Context: 1,000,000-token requested product window by default, separately show effective native window, logical history, active tokens, output reserve and compression losses; no arbitrary UI truncation. Model-native, GPU, RAM, storage, input size, and safety admission limits remain. Only enable native 1M when model extension, backend reported context, measured allocation and quality pass. Otherwise explicit managed/virtual mode with user consent; never label summary as full attention. Beyond 1M archive/retrieve rather than promise infinite active context. ACE remains opt-in until real telemetry/quality gates tested.
- Hardware: RAM/VRAM/SSD usage, native KV/expert occupancy, TTFT/decode, predicted fit, restart confirmation.
- Tools: search toggle and provider test; file picker grants scoped workspace read; edit separately requires diff approval, read-before-write, revision check, no escape through symlink/reparse points, atomic writes and rollback. No arbitrary shell by default; enforce OS isolation and bounded operations. Search and writes off by default.
- Settings: bilingual labels, editable engine parameters, credential-store references, diagnostics and logs; apply atomically at idle with validate -> preview -> confirm -> supervised restart -> verify -> rollback. UI handles all routine actions; no external JSON editing in final product.

## Multimodal
FreeToken supports image inputs for selected checkpoints and configurations, not every MoE model. Add capability negotiation, attachment validation, image token accounting and native processor/encoder routing. Distinguish document text extraction from visual reasoning. Reject unsupported video/audio; do not claim vision until real inference tested. Current planner accepts plain text only. No blanket request passthrough.

## Implemented here
GET /local/desktop/capabilities is an authenticated read-only contract; POST /local/desktop/settings/preview validates only supported inference settings and returns a theoretical estimate without saving or changing live state. Not an actual UI, no search/file execution or new multimodal support. It deliberately exposes unsupported flags as disabled. Existing managed ACE endpoints remain.

## Delivery gates
P0 obtain editable FreeToken Desktop source/license, pin backend and Harness releases, model/vision capability fixtures. P1 frontend IPC/settings workflow and verified restart rollback; real model + tool-call template parity, agent loop and opt-in approved tools. P2 images and document attachments, session/ACE integration, task quality/recovery tests. P3 native state/attention changes and measured 8K/32K/128K/256K/512K/1M; benchmark against original FreeToken. P4 independently branded installer, SBOM/licenses, offline inference, safe updates, permission tests Windows/Linux. Retain source notices.
