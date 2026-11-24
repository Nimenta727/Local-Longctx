# MillionContext / Local-Longctx — V2.0 implementation map

## Boundaries and selection

A separate control plane avoids coupling the UI to tensor memory management. Reuse OpenClaw's existing UI and Gateway via a local provider. An immediate fork would impose a large synchronization and packaging burden; a direct protocol adapter lets inference be validated independently first. Later, pin an upstream commit, retain license notices, and rebrand reviewed UI assets, packaging IDs and update channels. No upstream source modification in this preview.

    OpenClaw Control UI -> Gateway -> provider adapter
      -> Local-Longctx HTTP service -> request planner
      -> llama.cpp server -> CPU / GPU
      -> local GGUF and engine-owned state

Why llama.cpp: CPU baseline, GGUF quantization, mixed CPU/GPU execution and adjustable KV types. vLLM remains high-throughput reference; LMCache remains state management reference. Neither is a required dependency on a small desktop. Hybrid attention (Nemotron 3 Nano, Qwen3.6) reduces growing KV layers, while MoE still requires access to all weights.

## Current contracts

Config.validate -> memory_plan (theoretical only) -> Backend.start -> /health, /props, /v1/models -> Server. On each request planner uses /apply-template and /tokenize, then forwards to /v1/chat/completions and streams SSE without buffering whole responses. Single active request. No context shift; explicit configured model/context/output budget; no mode downgrade. Actual model native maximum is user metadata in v0.1; GGUF architecture parsing and verified model registry remain required. No automatic tool execution. Upstream OpenClaw compaction and template compatibility require independent testing. Model and binary provenance is the user's responsibility until signed release manifests exist.

## Next implementation boundaries

1. Freeze engine and OpenClaw revisions; run real integration tests on Windows/Linux and verify model templates and complete context limits.
2. Build model registry with architecture metadata and GGUF shards; measured per-device resource budget, hardware probes and explicit approved fallback.
3. Add state manifest containing model SHA256, engine revision, template digest, token prefix hash, quantization, position and recurrent-state schema; transactional writes and single-session checks. Keep raw KV out of JSON. Validate state consistency before restoration. No SSD hot KV by default.
4. Profile CPU/GPU transfer and MoE; use upstream optimizations where available, implement C++ scheduling only for measured gaps.
5. Add optional explicit Virtual mode (SQLite FTS5), provenance, never label as true million context.
6. Pin and review OpenClaw source, replace brand and package identity while retaining notices; implement UI additions for hardware and model management; integrate desktop launcher/installer after permissions and offline lifecycle tests. Replace Agent only behind stable interface.
7. Real million-token benchmarks, accuracy, cold/warm TTFT, decode TPS, peak RAM/VRAM, failure recovery and release gates.

## Hardware requirements — research targets, not measured minimum

| Tier | CPU | VRAM | RAM | SSD | Goal |
|---|---|---:|---:|---:|---|
| A | 4–8 cores AVX2 | 0 | 16 GiB | 256 GB | Small-model CPU smoke tests |
| B | 6–8 cores | 4–6 GiB | 32 GiB | 512 GB NVMe | 30B MoE compressed exploration |
| C | 8–12 cores | 8–12 GiB | 64 GiB | 1 TB NVMe | Recommended research baseline |
| D | 12+ cores | 16–24 GiB | 64–128 GiB | 1 TB NVMe | Performance comparison |

Prefer dual-channel RAM, PCIe 4.0 where available and sustained SSD throughput of at least 2 GB/s for model loading and future snapshots. Windows/Linux x64 first; macOS and other GPU backends require independent validation. No operating-system replacement.

Attention KV GiB = 2 × full_attention_layers × KV_heads × head_dim × total_tokens × bytes_per_value / 2^30. F16=2; Q8_0=34/32; Q4_0=18/32. At 1M total, assumed Nemotron 6/2/128 gives 5.72/3.04/1.61 GiB; assumed Qwen3.6 10/2/256 gives 19.07/10.13/5.36 GiB. Verify exact model config before use. Weight file size is separate; split GGUF and extra tensors must be counted. Reserve OS/UI, recurrent state, workspace and allocator overhead. RAM and VRAM are separate physical budgets; SSD is not equal to RAM.

Cold prefill time = input tokens / measured average prefill throughput. At 100/500/1000 tok/s, 1M tokens takes about 167/33/17 minutes; these are arithmetic examples, not predicted speed. Measure actual long-context throughput rather than extrapolate from short prompts.

Sources: https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md ; https://docs.openclaw.ai/gateway/local-models ; https://docs.openclaw.ai/gateway/config-tools/custom-providers ; https://docs.openclaw.ai/gateway/config-gateway ; https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16 ; https://huggingface.co/Qwen/Qwen3.6-35B-A3B .
