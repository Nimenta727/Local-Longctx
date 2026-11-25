# 桌面开发预览 / Desktop development preview

Local-Longctx Studio 将桌面界面、会话事务和工具权限交给固定版本的 DeepSeek Harness，通过本地网关调用 FreeToken。源码预发行需要自行准备构建环境。 [固定版本 / Pinned revision](harness.lock.json)

## 构建和启动 / Build and launch

1. 安装 Python 3.10+、Node.js ^24.22.3 或 >=26.13.1、pnpm 11.28.5，并按固定 Harness 版本的说明准备原生构建依赖。本地推理需要可用的 NVIDIA GPU、匹配驱动、可信 FreeToken 和兼容 MoE GGUF。
2. 在本仓库根目录执行下列命令。准备脚本会检出固定 Harness 版本并应用覆盖层，目标为 `desktop/upstream`。从旧版升级时，用新源码准备一份新的覆盖层。

```bash
python desktop/prepare_harness.py
cd desktop/upstream
pnpm install --frozen-lockfile
cd ../..
python desktop/verify_build.py
python desktop/launch_dev.py
```

Install the pinned dependencies, materialize the overlay, verify the build, and launch the development desktop. The launcher uses `desktop/upstream`. A fresh overlay is needed when upgrading.

## 选择模型 / Choose a model

1. 在模型设置中选择 FreeToken 可执行文件和 GGUF。填写已核实的模型上限、原生窗口和输出预留。可从 8,192 Token 起步，容量以模型和显卡能实际支持的范围为准。
2. 确认来源与兼容性后启动引擎。等待状态显示就绪，然后在自定义供应商里使用 **Local-Longctx 本地模型预设**，并在会话中选中它。
3. 若旧供应商仍使用临时密钥，在本地引擎就绪后点击「复制本地 API 密钥」，更新该供应商一次。当前数据目录会保存网关密钥。

Select the executable and GGUF, verify compatibility, and start the engine. Then configure and select the Local-Longctx preset. Update an old temporary provider key once if needed.

## 会话、工具输出和缓存 / Context, tool output, and cache

- 每轮发送前，Harness 会估算当前历史、新消息、系统提示增量、工具定义和输出预留。临近阈值时先处理可缩减的工具结果，再尝试压缩历史。FreeToken 对最终的原生 Messages 请求计数，超限时网关会列出输入、输出、安全余量和窗口。
- 本地压缩生成检查点，并尝试保留原文中的约束、决策、失败原因和待办，以及对应的会话事件序号。后续轮次有余量时，应用先匹配文件名、错误码等字面线索，再用本地中英术语表补充召回。检索范围是当前会话，词表之外的改写可能漏检。
- 大型纯文本工具结果可保存到会话所属的本地文件。模型看到首尾、预算内的原始错误行和读取路径。以 8K 窗口为例，单份预览的估算上限为 1,024 Token。
- Cache 面板显示 KV、MoE、SWA 和 GDN 容量。空闲时确认重建，应用会保存引擎实际分配的容量。重启时重新核对容量和预算。配置损坏时可重新应用容量设置，推理中的缓存张量会随引擎重建。

The local preset budgets each request, preserves source-linked task excerpts, and recalls evidence from the current session. Large tool results can be read from their local spill path. The Cache panel persists approved capacities and checks them against actual allocation after restart. FreeToken rebuilds live cache tensors.

## 数据位置与升级 / Data and upgrades

模型设置中的「打开本地数据目录」可定位会话、附件、设置、日志和运行时缓存。默认目录如下。

| 平台 / Platform | 路径 / Path |
| --- | --- |
| Windows | `%LOCALAPPDATA%/Local-Longctx` |
| Linux | `${XDG_DATA_HOME:-$HOME/.local/share}/Local-Longctx` |
| macOS | `~/Library/Application Support/Local-Longctx` |

旧 Studio 数据若还在当前源码 checkout 中，启动器会继续使用它。换到新 checkout 时，可以在启动前将 `LOCAL_LONGCTX_DATA_DIR` 指向旧目录或其完整副本。备份和迁移前先关闭桌面与推理服务。模型权重、FreeToken 程序和项目文件仍使用所选路径。桌面配置默认关闭会话日志上传和会话遥测。

Open the app data directory from model settings. Close the desktop and engine before copying it for backup or migration. Set `LOCAL_LONGCTX_DATA_DIR` before launch to select an existing profile or its copy.

## 排错 / Troubleshooting

- **启动失败或超时**。在数据目录查看 `desktop-worker.log` 和 `freetoken.log`，检查引擎文件、模型兼容性、显卡资源和端口。
- **缓存方案不可用**。确认模型、引擎、GPU 和启动参数，按当前原生预算重新应用。
- **上下文超限**。查看错误中的实际计数，缩短输入或调整输出预留。先核实模型与显存容量，再增大原生窗口。

完整 Electron 运行和 NVIDIA 端到端验收仍待完成。 / Full Electron and NVIDIA end-to-end validation remains pending. [验证范围 / Verification](../docs/testing.md)
