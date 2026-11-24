# Local-Longctx / MillionContext

v0.2.0 · Apache-2.0 · NVIDIA MoE research preview

唯一推理后端：FreeToken。自研 ACMA 长上下文管理、AHS 硬件调度和 ACE 自适应 Compact；可选复用 OpenClaw Control UI。V2.x 多后端设计废止。

Python 3.10+；从 https://github.com/FlashML-org/FreeToken 获取可信本地 ft 与支持的 MoE GGUF，核实版本、GPU、模型窗口及许可证。复制 configs/example.json 为 configs/config.local.json，填写路径和核实过的兼容性标记。先小窗口试验：

    python -m unittest discover -s tests -v
    python -m longctx --config configs/config.local.json hardware
    python -m longctx --config configs/config.local.json plan
    python -m longctx --config configs/config.local.json doctor
    python -m longctx --config configs/config.local.json serve

本地 API http://127.0.0.1:18080/v1；使用私有 LOCAL_LONGCTX_API_KEY 或终端生成的会话密钥。仅文本、单请求、SSE；不支持工具调用。硬件不满足时拒绝启动，不换引擎。跨 API token 预检是估算，模板一致性仍需验证。

## Adaptive Compact Engine

    python -m longctx compact-plan configs/compact.example.json

ACE 依据 RAM、VRAM、增长率、KV 占用、重要性、访问频率、历史依赖与压缩/重放成本，返回决策和候选段 ID。精确模式及未经授权的语义压缩受保护。此命令仅分析输入快照，不修改历史、不执行模型摘要或迁移 KV。在线采样、执行、回滚尚待研发。

OpenClaw 可通过 openclaw-config 导出独立配置，或使用 desktop --openclaw /absolute/path/to/openclaw 试验启动器；暂未自有品牌发行。现有工具及插件默认禁用。

见 [V3设计](docs/architecture/acma-v3.md) 与 [研发记录](docs/routine/2026-11-24-acma-ace.md)。未完成实际 GPU/OpenClaw 测试；不声称百万原生上下文已实现。第三方项目各自许可。
