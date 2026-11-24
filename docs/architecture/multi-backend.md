# V2.1 多后端架构（取代 V2.0 中的单引擎决策）

OpenClaw UI → Local-Longctx API → Context Manager → Hardware Scheduler → FreeToken / llama.cpp adapter → native kernels.

## 选型与职责
FreeToken 面向 NVIDIA 大型 MoE，复用带宽自适应 CPU/GPU 计算、专家缓存、语义状态检查点和原生缓存管理。llama.cpp 保留广泛的 GGUF/CPU 兼容基线。两者不是同一内存格式，不能直接互换 KV。参考 https://github.com/FlashML-org/FreeToken 、https://github.com/FlashML-org/FreeToken/blob/main/docs/cli.md 、https://arxiv.org/abs/2608.16157 。FreeToken 上游 Apache-2.0；当前仅调用外部安装，不复制源码，发行前核查固定版本及所有依赖许可。

## 硬件调度
现有实现：CPU 逻辑线程、系统 RAM（Linux/Windows）、磁盘空闲、NVIDIA UUID/显存/驱动；按本地可执行文件、用户确认的 MoE 兼容性、空闲显存及 RAM 选择后端。线程、GPU UUID、VRAM 比例、prefill chunk、KV reserve 传递给 FreeToken；llama.cpp 的卸载与精度仍由用户配置。RAM 门槛为权重文件大小加 4 GiB 的初始启发式，不是实际占用证明。后续测 PCIe/DRAM 带宽、CPU ISA、NUMA、非 NVIDIA GPU、CUDA/模型版本兼容、分层资源配置和压力重规划。不可在活跃会话静默换引擎。

## 自研长上下文层
现有实现：统一 token 预算、checkpoint 元数据及精确 prefix token hash 比对（独立模块，尚未接入引擎状态导出）。身份必须一致：引擎及修订、模型、tokenizer、模板、状态格式、精度、RoPE、会话。FreeToken 使用原生复用；llama.cpp 使用自身缓存。FreeToken Anthropic count_tokens 对 OpenAI 请求只作估算，启动要求 /v1/models 确认 context 长度；必须实测 tokenizer parity 与边界，不能保证无截断。禁止把原生 KV 类型当成 GGML Q4/Q8。

未来 VRAM：活跃 KV、递归状态、热专家及计算工作区；RAM：原生支持的 host KV、专家、预取与 pinned buffers；SSD：不可变 opaque checkpoint、身份/内容 hash、原子提交、配额、LRU 和安全恢复。只有实际后端支持 export/restore 才允许迁移。跨引擎不复用原始 tensor；重新预填充。先测原生 attention 与 cache hit，再研究可验证的稀疏/分块/混合精度算法。不能降低语义质量却声称真正完整上下文。

## 硬件目标（未实测）
CPU 16GiB RAM：小模型 llama.cpp；4–6GiB VRAM/32GiB RAM：混合 llama.cpp；8–12GiB VRAM/64GiB RAM：FreeToken NVIDIA 研究档；16–24GiB VRAM/64–128GiB RAM：性能档。SSD 256GB–1TB NVMe，按模型体积和冷状态预算。实际取决于模型及缓存，绝不保证百万 token。

## 验证顺序
固定版本及模型 → 小规模真实 API/CLI/进程树测试 → 同模型跨后端准确性、TTFT、吞吐、峰值 RAM/VRAM → 测量原生缓存命中、上下文上限 → 后端能力协商及冷存储 → 32K/128K/256K/512K/1M → OpenClaw 品牌发行。现阶段仅 GGUF、文本、实验适配，HF/FTW 及真实 GPU 测试待完成。
