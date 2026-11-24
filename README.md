# Local-Longctx / MillionContext

**v0.1.0 — development preview / 研发预览** · Apache-2.0

目标：消费级电脑上的离线本地长上下文推理平台，优先降低显存需求。使用 llama.cpp 的真实模型推理，复用 OpenClaw Control UI，不另写聊天前端。本版本不是已验证的百万上下文发行版，也不是完整 OpenClaw fork。

## V2.1 architecture update / 新架构

FreeToken 为 NVIDIA 大型 MoE 高性能候选后端，llama.cpp 保留兼容基线。独立硬件层自动探测 CPU、RAM、磁盘和 NVIDIA 可用显存，选择引擎并限定线程、GPU 和原生资源参数；独立上下文模块提供预算与前缀身份校验，未来研究三级缓存迁移及注意力优化。

使用 configs/freetoken.experimental.json，配置本地 ft 和 GGUF 路径。只有核实实际模型与 FreeToken 版本兼容后才设置 freetoken_model_verified 为 true。engine=auto 仅在启动前选择，engine=freetoken 不满足条件时拒绝，engine=llama 保留旧行为。运行 python -m longctx --config configs/config.local.json hardware 查看选择结果，再执行 doctor 与 serve。FreeToken 跨 API token 预检仅为估算，不能宣称无截断或百万上下文已验证；缓存精度由 FreeToken 原生策略决定。SSD tensor cache、注意力内核和实际状态迁移仍待开发。详见 [V2.1 多后端设计](docs/architecture/multi-backend.md)。

## 已实现 / Implemented

- GGUF 本地导入与启动参数验证；CPU/GPU 层数、CPU MoE、KV 位置与量化、批量及微批可配置。
- 本地进程生命周期管理、启动健康检查、报告上下文大小校验。
- 回环地址、Bearer 鉴权、单请求并发、模板与真实 tokenizer 预检、明确拒绝超预算输入；禁用 context shift 与自动 fit。
- OpenAI-style 文本 chat completions（JSON/SSE），模型列表和资源预算接口。
- OpenClaw 独立配置生成与可选 Control UI 启动器；复用现有 UI，工具调用暂不支持。
- Needle 检索 smoke benchmark、单元测试和硬件预算文档。

## Quick start / 快速开始

1. 安装 Python 3.10+。从 [llama.cpp 官方仓库](https://github.com/ggml-org/llama.cpp) 获取与你硬件匹配的可信 llama-server（CPU/CUDA/Vulkan）；从模型发布方获取合法 GGUF。记录版本、文件哈希、许可证。不要运行来源未知的二进制。此仓库不附带权重或上游二进制。
2. 克隆本仓库，在仓库根目录执行以下命令。直接用 Python 模块运行，无需安装第三方 Python 依赖。

       python -m unittest discover -s tests -v
       python -m longctx --help

3. 将 configs/example.json 复制为 configs/config.local.json，修改 server、model、model_limit、context、threads 等字段。相对路径以配置文件目录为准；Windows 使用 llama-server.exe。先使用小模型和 8K–32K 上下文验证，不直接启动 1M。
4. 检查参数、估算容量、启动：

       python -m longctx --config configs/config.local.json doctor
       python -m longctx --config configs/config.local.json plan
       python -m longctx --config configs/config.local.json serve

   使用终端中生成的私有 API key，或事先设置 LOCAL_LONGCTX_API_KEY 为至少 24 字符的随机 ASCII 密钥。服务仅监听 127.0.0.1:18080；在同机客户端中配置 base URL http://127.0.0.1:18080/v1、模型 ID local-longctx 和该密钥。Ctrl+C 关闭。

5. 可选 OpenClaw：安装经过核实的上游版本，设置相同 LOCAL_LONGCTX_API_KEY 和独立 LOCAL_LONGCTX_GATEWAY_TOKEN（强随机密钥），生成配置：

       python -m longctx --config configs/config.local.json openclaw-config

   将输出保存到**新的** OpenClaw 配置文件，不覆盖原有配置。按 [OpenClaw 环境变量说明](https://docs.openclaw.ai/help/environment) 设置 OPENCLAW_CONFIG_PATH、OPENCLAW_STATE_DIR，启动本地 gateway 并通过上游 dashboard 打开 Control UI。保持原有安全审批和系统隔离，不配置远程渠道、插件或云端回退。

   可选一体启动预览（仅支持真实本地可执行文件，不支持 Windows npm .cmd shim）：

       python -m longctx --config configs/config.local.json desktop --openclaw /absolute/path/to/openclaw

   自动启动推理与 Gateway，调用上游 dashboard。当前要求新的 state_dir；已有独立配置时使用手动启动路径。上游版本尚未冻结或实机集成测试，配置兼容失败时查看 gateway.log，不关闭安全限制。此功能不是独立原生安装包，也未替换上游商标。

## Context semantics / 上下文语义

Full：FP16 KV，全部已纳入请求的文本，默认不改变注意力结构。Compressed：Q8_0/Q4_0 KV，仍输入完整请求但状态量化。Virtual：外部检索模式尚未实现。上下文总量包含聊天模板、系统消息、输入和输出预算。1,000,000 总长度不等于 1,000,000 输入加任意输出。预检采用上游模板及 tokenizer 加保守余量；仍需与实际 usage 对照验证。上游 Agent 可能主动总结历史，不等同真实完整上下文。

## Benchmarks / 验证

设置与服务相同的 LOCAL_LONGCTX_API_KEY 后，提供自己的 UTF-8 测试语料：

    python benchmarks/needle.py corpus.txt --model local-longctx --position 0.5 --output benchmark-results/run.json

结果记录 TTFT、总耗时、精确匹配与服务器报告 usage。逐步增加 32K、128K、256K、512K、1M，重复至少三次并记录硬件及引擎版本。必须结合真实 Token 计数、峰值内存、多跳推理与跨文件任务，不能用单次检索成功宣称百万上下文通过。示例 1M 配置是实验目标，不能保证启动。

## Status / Roadmap

详见 [设计与硬件要求](docs/architecture/design.md)、[验证计划](docs/testing.md) 和 [本次开发记录](docs/routine/2026-11-24-bootstrap.md)。
当前仅控制平面与适配器，不是自研 C++ 内核。Prefix/KV 的实际管理由所选引擎承担；SSD 统一快照、GDN/Mamba 状态恢复、动态专家调度、稀疏内核、完整 Agent 替换、Windows 安装包与品牌 fork 均待实现。无模型/GPU 实测结果；测试文件不代表测试已经运行。

## License / Credits

自有代码 Apache-2.0；FreeToken、llama.cpp 与 OpenClaw 为独立上游项目，按各自许可证使用。本仓库尚未复制其源码或发行资产。模型权重、图标、字体、依赖许可需独立审查；不得冒用上游商标。详见 THIRD_PARTY.md。
