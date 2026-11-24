# 架构 / Architecture

## 组件 / Components
Harness GUI & agent → authenticated Local-Longctx gateway → AHS + ACMA/ACE control plane → FreeToken NVIDIA MoE. FreeToken remains the only execution engine. Harness owns tool permissions and session transactions; local gateway never executes tools itself. Harness 图形界面与 Agent 通过本地鉴权网关接入 AHS、ACMA/ACE，FreeToken 是唯一计算后端；工具执行与会话事务由 Harness 管理。

## 上下文 / Context
1,000,000 Token 是逻辑历史研发目标，不是已通过验证的原生窗口；模型上限、实际 KV 池、输入与输出预留分别校验。The million-token target is logical history, not a verified native window. Model limit, actual KV pool and input/output budget are distinct. Native Messages counts tools and results through /v1/messages/count_tokens, then enforces output reserve and margin. OpenAI text counting is an estimate / OpenAI 文本计数仍为跨协议估算。

## ACE
综合 RAM/VRAM/KV/窗口最大压力、增长率、信息重要性与访问频率、任务历史依赖、压缩与前缀重算成本。Initial heuristic: high-water 0.80, emergency 0.95, target 0.65, 60s cooldown, cost margin 20%. 初始阈值需实测校准 / Thresholds need empirical calibration. Exact/no-consent/busy/protected history blocks semantic compaction. Harness observer reads balanced range totals and native telemetry, but does not automatically rewrite sessions / Harness 只读观察，不自动改写会话。

Separate managed session API uses SQLite revisions, hash-based compare-and-swap and extractive summaries. Full originals archived; rollback creates a new revision. 独立受管会话使用 SQLite、哈希校验、摘录式压缩和版本回滚，非原生 KV 快照。使用 [原始 API 规范 / original detailed API specification](https://github.com/Nimenta727/Local-Longctx/blob/research/v5.2-archive/docs/architecture/ace-managed.md)；请求 JSON 字段不变 / Request fields unchanged. Use private local storage; archive not encrypted / 本地历史未加密。

## Cache / 缓存
GET /local/cache/status reports actual geometry, per-pool unit costs and limits. POST /local/cache/apply requires current revision, explicit confirmation and idle engine; native engine makes final capacity decision. 原生 KV、专家、SWA、GDN 池基于几何与预算调节；空闲确认后才允许重建。Live resize may invalidate prefix reuse and is not persisted / 实时调整可能使缓存失效，不跨重启保存。

## Research / 研究
独立 CUDA 张量注意力、4/8-bit KV、查询感知页面选择、RAM/SSD 页面存储迁至 [research/v5.2-archive](https://github.com/Nimenta727/Local-Longctx/tree/research/v5.2-archive)，不影响核心运行。Research prototypes are isolated from main; no production CUDA fused kernel or native three-tier KV migration is implemented. Real benchmark ladder: 8K → 32K → 128K → 256K → 512K → 1M, only within verified model and hardware bounds. 比较 TTFT、Decode、峰值 RAM/VRAM、缓存命中与答案质量；不得将近似注意力标为完整注意力 / Compare latency, throughput, peak memory, cache hits and quality; label approximation honestly.
