# Local-Longctx / MillionContext

v0.2.0 · Apache-2.0 · NVIDIA MoE research preview

唯一推理后端：FreeToken。自研 ACMA 长上下文管理、AHS 硬件调度和 ACE 自适应 Compact；V4 目标复用 FreeToken Desktop 前端（源码授权尚待核实），旧 OpenClaw 启动器暂保留。V2.x 多后端设计废止。

Python 3.10+；从 https://github.com/FlashML-org/FreeToken 获取可信本地 ft 与支持的 MoE GGUF，核实版本、GPU、模型窗口及许可证。复制 configs/example.json 为 configs/config.local.json，填写路径和核实过的兼容性标记。先小窗口试验：

    python -m unittest discover -s tests -v
    python -m longctx --config configs/config.local.json hardware
    python -m longctx --config configs/config.local.json plan
    python -m longctx --config configs/config.local.json doctor
    python -m longctx --config configs/config.local.json serve

本地 API http://127.0.0.1:18080/v1；使用私有 LOCAL_LONGCTX_API_KEY 或终端生成的会话密钥。仅文本、单请求、SSE；不支持工具调用。硬件不满足时拒绝启动，不换引擎。跨 API token 预检是估算，模板一致性仍需验证。

## Adaptive Compact Engine

    python -m longctx compact-plan configs/compact.example.json

ACE 依据 RAM、VRAM、增长率、KV 占用、重要性、访问频率、历史依赖与压缩/重放成本，返回决策和候选段 ID。精确模式及未经授权的语义压缩受保护。此命令仅分析输入快照，不修改历史、不执行模型摘要或迁移 KV。新增独立受管会话 API，支持只读 FreeToken 遥测、显式预览/提交的摘录式压缩、原文归档与回滚；普通聊天不改写。在线自动评分与 OpenClaw 接入仍待研发。详见 [受管会话接口](docs/architecture/ace-managed.md)。

OpenClaw 可通过 openclaw-config 导出独立配置，或使用 desktop --openclaw /absolute/path/to/openclaw 试验启动器；暂未自有品牌发行。现有工具及插件默认禁用。

见 [V3设计](docs/architecture/acma-v3.md) 与 [研发记录](docs/routine/2026-11-24-acma-ace.md)。未完成实际 GPU/OpenClaw 测试；不声称百万原生上下文已实现。第三方项目各自许可。

[本次开发记录](docs/routine/2026-11-24-ace-managed.md)

## V4 桌面路线

[统一桌面架构与验收要求](docs/architecture/desktop-v4.md)。新增认证 API `GET /local/desktop/capabilities` 和 `POST /local/desktop/settings/preview`；只读能力/参数预览，不执行设置应用，不代表图形界面已改造。目标默认百万逻辑窗口，原生窗口独立核实。DeepSeek Harness 搜索、文件工具与多模态待集成。见 [研发记录](docs/routine/2026-11-24-desktop-v4.md)。

## V5 桌面产品路线

正式桌面基础改为 DeepSeek Harness；FreeToken 仅作为 MoE 计算后端。新增 [锁定上游源码 overlay 与 GUI 模型设置预览](desktop/README.md)。保留上游工具及 MIT 归属；尚未验证本地工具调用、自动 ACE、完整品牌和安装包。V4 FreeToken Desktop 方案已被替代。见 [本次开发记录](docs/routine/2026-11-24-harness-studio.md)。

## V5.1 Native tools / ACE / ACMA

新增本地 Anthropic Messages 原生工具传输预览、Harness 压缩边界 ACE 只读接入及 CPU 分块注意力参考。当前不宣称工具执行、自动压缩或 GPU 加速已验证；详见 [技术接口与边界](docs/architecture/harness-native-ace.md) 和 [研发记录](docs/routine/2026-11-24-native-tools-ace-attention.md)。

## V5.2 Cache workbench

新增 [缓存参数工作台与研究验收说明](docs/architecture/cache-workbench.md)，支持原生缓存几何读取、实验性空闲调整及启动配置；新增真实协议 smoke、桌面构建入口、分块 GPU 张量计算、混合 KV 量化和 RAM/SSD 存储研究。未经过实机测试，自动 ACE、融合内核与原生三级迁移仍待完成。见 [研发记录](docs/routine/2026-11-24-cache-workbench.md)。
