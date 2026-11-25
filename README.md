# 远栈 FarStack

远栈是面向 NVIDIA GPU 的本地推理工作台。桌面入口直接打开远栈工作区，会话和缓存设置保存在本机。FreeToken 执行推理，Python 网关负责上下文预算、归档和模型接口。

FarStack is a local inference workbench for NVIDIA GPUs. Its desktop workspace stores conversations and cache settings locally. FreeToken runs inference, while the Python gateway handles context budgets, archives, and model APIs.

## 启动桌面 / Start the desktop

安装 Node.js 24 和 Python 3.10+。本地推理还需要兼容的 MoE GGUF、Windows 原生运行时或外部 FreeToken 程序，以及匹配的 NVIDIA 驱动。

```bash
git clone --branch main https://github.com/Nimenta727/Local-Longctx.git
cd Local-Longctx
npm ci --prefix desktop
python desktop/launch_dev.py
```

在「模型与缓存」页选择 GGUF 并启动。引擎就绪后，可以拖动 KV、MoE 专家和滑窗 KV 滑杆查看容量与显存估算，空闲时点击「应用缓存」。展开「启动参数」可设置下次启动的预算和策略。实验性 SSD 默认关闭，手动开启后显示相应参数。 [桌面使用指南](desktop/README.md)

在「本地会话」选择工作目录后，支持工具调用的模型可读写和搜索文件、在确认后运行命令，并把结果留在本地会话。 [工具使用说明](desktop/README.md#让本地模型使用工具)

## 网关与构建 / Gateway and builds

- 启动网关并使用 Messages、Chat Completions 或受管会话 API。 [CLI 与 API](docs/usage.md)
- 了解滚动上下文、归档与缓存预算。 [架构](docs/architecture.md)
- 准备 FreeToken 运行时、构建 Windows 安装包或执行验证。 [构建与验收](docs/farstack.md)
- 百万 Token 是经预算治理的逻辑会话历史目标。逻辑历史、模型原生窗口和活动 KV 容量各有独立的限制。 [评测说明](docs/testing.md)

GitHub 上的 `v0.3.0-alpha.5` 是较早的源码预发行。当前桌面入口与设置界面来自 `main`。 [历史发行](https://github.com/Nimenta727/Local-Longctx/releases/tag/v0.3.0-alpha.5)

项目采用 Apache-2.0。FreeToken、Electron 和模型权重沿用各自许可。 [第三方许可](THIRD_PARTY.md)
