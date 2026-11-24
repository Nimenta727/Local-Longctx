# V3: FreeToken + ACMA + AHS + ACE

Only FreeToken for NVIDIA MoE. No CPU-only or alternative runtime fallback. OpenClaw remains optional and unmodified. ACMA owns policy, not CUDA tensor allocation.

## ACE
Inputs: available and total RAM/VRAM, context growth, native window and output reserve, measured KV occupancy, importance/access/dependency scores, expected turns, cache hit fraction, compaction cost, invalidated prefix tokens, and scratch memory.

Pressure = max(RAM pressure, VRAM pressure, KV occupancy, context occupancy). Initial thresholds .80/.95; target .65; forecast horizon max(60 s, twice compact duration); 60 s cooldown. These are tunable research heuristics, not measured universal constants. Separate allocated memory from reclaimable KV. Unknown telemetry must not be replaced with zero.

Cost = summary time + invalidated prefix / measured prefill rate. Benefit = saved tokens / prefill rate x expected turns x uncached fraction. Excludes decode/IO savings until measured; require 20% margin absent emergency. Exact mode, lack of consent, strong history dependency, pinned/recent segments and insufficient scratch space block semantic compression. Urgent pressure with no safe action pauses admission rather than silently truncating.

Semantic compaction differs from KV quantization and unused-cache eviction. Proposal is not execution. Future transaction archives exact originals with provenance and hash, preserves constraints/code/decisions, verifies summary facts, retokenizes, atomically swaps prompt while idle, invalidates incompatible checkpoints, rolls back on failure. Shorter prompt does not guarantee VRAM returned to OS.

## Integration
FreeToken exposes /v1/stats, /v1/cache/status and /v1/requests; pin revision and test schema. AHS supplies hardware data and startup limits, ACE evaluates idle snapshots, ACMA executes only supported state operations. Prefer native radix cache and supported 8-bit KV. Live rebuild (/v1/cache/rebuild) needs revision-specific tests and is not invoked. No speculative direct tensor API.

Later C++/CUDA: verified opaque checkpoint export, tiered paging, mixed precision, query-aware routing and online softmax reference. SSD archives original tokens and compatible opaque states; active SSD KV not implemented. Exact / quantized / sparse / virtual modes separately labeled.

## Research targets
16 GiB RAM + 6–8 GiB NVIDIA VRAM: smaller supported MoE, 8K–128K native first. 32 GiB RAM + 8–12 GiB VRAM: selected 30B quantized MoE if measured placement fits. 16–24 GiB VRAM: longer native context experiments. NVMe 512 GB–1 TB. Million logical tokens is not a million native window. No guaranteed minimum hardware. GGUF preview only.

References: https://github.com/FlashML-org/FreeToken/blob/main/docs/cli.md ; https://github.com/FlashML-org/FreeToken/blob/main/docs/performance/prefill.md ; https://github.com/FlashML-org/FreeToken/blob/main/docs/performance/decode.md .
