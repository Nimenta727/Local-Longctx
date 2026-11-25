# Local-Longctx Studio

**v0.3.0-alpha.4 · 源码预发行 / Source prerelease · Apache-2.0**

Local-Longctx Studio 是面向 NVIDIA GPU 的本地 MoE 工作台。桌面和 Agent 基于固定版本的 DeepSeek Harness，推理由 FreeToken 执行。应用在本机管理会话、长工具输出和缓存容量设置。

Local-Longctx Studio is a local NVIDIA MoE workbench. It combines a pinned DeepSeek Harness desktop and agent with FreeToken inference. The app manages conversations, large tool outputs, and cache preferences locally.

## 现在可以试用 / What you can try

- **桌面长会话**。模型接近窗口预算时，Harness 可将较早历史压缩成检查点，保留带出处的任务状态，并在之后的轮次按需找回当前会话的证据。
- **工具日志归档**。过长文本保留首尾和可用的原始诊断行，全文写入本地文件，模型可按路径读取。
- **本地网关与缓存**。网关提供原生 Messages、文本 Chat Completions 和独立受管会话 API。Cache 面板可在空闲时应用容量设置，并在重启时重新验证实际容量。

The desktop supports session checkpoints, source-linked task excerpts, and archival recall. Oversized text tool results can be stored locally with a short preview. The gateway exposes native Messages, text Chat Completions, and an explicit managed-session API. Confirmed cache capacities are revalidated after restart.

## 快速开始 / Quick start

离线检查需要 Python 3.10+，想跑本地推理还需要匹配的 NVIDIA 驱动、FreeToken 与兼容的 MoE GGUF。桌面预览另需固定 Harness 的构建工具链。 / Offline checks require Python 3.10+. Local inference also requires a compatible NVIDIA driver, FreeToken executable, and MoE GGUF. Desktop development needs the pinned Harness toolchain.

```bash
git clone --branch v0.3.0-alpha.4 https://github.com/Nimenta727/Local-Longctx.git
cd Local-Longctx
python -m longctx --version
python scripts/check_release.py
python -m benchmarks.context_baseline
```

- 从源码启动桌面、选择本地模型、备份或迁移数据。 [桌面指南 / Desktop guide](desktop/README.md)
- 启动 Python 网关并使用受管会话 API。 [CLI 与 API 指南 / CLI and API guide](docs/usage.md)
- 了解上下文预算、归档和缓存的关系。 [架构 / Architecture](docs/architecture.md)
- 查看离线回放、实机评测和验收范围。 [验证 / Verification](docs/testing.md)
- 下载这个版本的源码。 [GitHub Release](https://github.com/Nimenta727/Local-Longctx/releases/tag/v0.3.0-alpha.4) · [发行说明 / Release notes](RELEASE_NOTES.md)

**验证范围。** 百万 Token 是逻辑历史研发目标。当前版本提供源码归档，真实 GPU 上的原生窗口、自动压缩、缓存恢复和完整桌面运行仍待实测。 / One million tokens is a logical-history research target. This source prerelease has no verified native million-token run or complete Electron and GPU validation.

项目代码采用 Apache-2.0，Harness、FreeToken 和模型权重沿用各自许可。 / Project code is Apache-2.0. Upstream components and model weights retain their own licenses. [第三方许可 / Third-party notices](THIRD_PARTY.md) · [研究历史 / Research archive](https://github.com/Nimenta727/Local-Longctx/tree/research/v5.2-archive)
