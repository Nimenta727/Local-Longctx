# Local-Longctx Studio

**v0.3.0-alpha.3 · Source preview / 源码预发行 · Apache-2.0**

本地 NVIDIA MoE AI 工作台：以 FreeToken 为唯一推理后端，以开源 Harness 为桌面及 Agent 基础，研发自适应长上下文管理。独立项目，非上游官方产品。

A local NVIDIA MoE AI workbench: FreeToken is the sole inference backend; open-source Harness provides the desktop and agent foundation. Adaptive long-context management is under development. Independent project, not an official upstream product.

[中文使用指南 / English guide](docs/usage.md) · [架构 / Architecture](docs/architecture.md) · [测试 / Verification](docs/testing.md) · [发行 / Release](docs/release.md) · [研发记录 / Development log](docs/routine/README.md)

[新版发行说明 / Release notes](RELEASE_NOTES.md) · [桌面本地数据 / Desktop local data](desktop/README.md)

## 核心能力 / Core capabilities

| 中文 | English | 状态 / Status |
| --- | --- | --- |
| FreeToken MoE、本地资源调度 AHS | FreeToken MoE and AHS resource planning | Source preview / 源码预览 |
| Messages 工具协议、文本 API | Native Messages tool transport and text API | End-to-end unverified / 未完成联调 |
| ACE 自适应压缩、历史归档及回滚 | ACE policy, managed history archive and rollback | Automatic desktop checkpointing / 桌面自动管理 |
| GUI 模型配置、KV/MoE/SWA/GDN 容量控制 | GUI model settings and native cache pools | Unbuilt overlay / 未构建覆盖层 |
| 百万逻辑历史目标 | Million-token logical history target | Research target / 研发目标 |

**边界 / Boundaries:** 尚未完成原生百万 Token、真实 GPU 性能、完整桌面运行、自动压缩实机、多模态与完整工具执行验证。没有已验证的 Windows 安装包。模型窗口不等于 KV 容量。No verified native 1M, GPU performance, desktop runtime, real-engine automatic compaction, multimodal or full tool execution. No verified Windows installer. Model window is not KV capacity.

## 快速开始 / Quick start

需要 Python 3.10+、可信本地 FreeToken 及其支持的 MoE GGUF、NVIDIA GPU 和匹配驱动。桌面开发需要上游指定 Node.js/pnpm。Requires Python 3.10+, trusted FreeToken and compatible MoE GGUF, NVIDIA GPU and matching drivers. Desktop development requires the pinned upstream Node.js/pnpm toolchain.

```bash
git clone https://github.com/Nimenta727/Local-Longctx.git
cd Local-Longctx
python -m longctx --version
python -m unittest discover -s tests -v
python -m longctx compact-plan configs/compact.example.json
```

桌面：按照 [桌面指南 / Desktop guide](desktop/README.md) 准备固定 Harness 源码、依赖和构建，再运行开发 GUI。后端 CLI：复制 configs/example.json 为 configs/config.local.json，核实模型和引擎，运行 hardware、plan、doctor、serve。Desktop: prepare pinned Harness sources and dependencies, build and launch development GUI. CLI: copy the example config, verify model/engine, then run hardware, plan, doctor and serve.

## 仓库结构 / Repository layout

- `longctx/` — 推理控制、协议、ACE、原生缓存 / inference control, protocol, ACE, cache.
- `desktop/` — 固定 Harness 集成 / pinned Harness integration.
- `configs/` — 参数示例 / example configurations.
- `tests/`, `benchmarks/` — 核心验证及真实协议测试入口 / core verification and protocol smoke entry points.
- `docs/` — 双语文档与研发记录 / bilingual documentation and development history.

main 不包含独立研究实验、旧 OpenClaw 入口或过时设计。完整 V5.2 历史与 CUDA、KV 量化、稀疏注意力及 RAM/SSD 研究保存在 [research/v5.2-archive](https://github.com/Nimenta727/Local-Longctx/tree/research/v5.2-archive)。Main contains no standalone experimental kernels or obsolete OpenClaw entry points. The full V5.2 history and research are preserved on the research archive branch.

## 许可 / License

自有代码 Apache-2.0；第三方源码与模型使用各自许可证。保留上游版权及 MIT 声明，不使用上游商标冒充官方发行。Own code is Apache-2.0; upstream software and models retain their own licenses. Preserve copyright and MIT notices; no official endorsement. See [THIRD_PARTY.md](THIRD_PARTY.md).
