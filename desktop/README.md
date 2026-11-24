# Local-Longctx Studio — 桌面源码预览 / Desktop source preview

采用固定 DeepSeek Harness 源码覆盖层，不复制整套上游仓库，不删除原有工具、权限及沙箱。不是安装包。Pinned source overlay, not a bundled installer. Upstream tools, permission checks and sandbox remain intact.

## 开发准备 / Developer setup
1. 核对 [harness.lock.json](harness.lock.json) 中固定修订及上游 MIT 许可 / Review the pinned revision and upstream MIT license.
2. 执行 `python desktop/prepare_harness.py`。脚本不覆盖现有 checkout，锚点变化时停止 / Prepare a fresh checkout; stop on mismatched anchors.
3. 安装上游要求的 Node.js ^24.22.3 或 >=26.13.1、pnpm 11.28.5，并按照上游说明安装锁定依赖与原生工具链 / Install upstream-required Node/pnpm and native dependencies following upstream instructions.
4. 执行 `python desktop/verify_build.py`，然后 `python desktop/launch_dev.py` / Run build verification, then launch the development GUI. Do not use upstream publish targets / 不使用上游发行命令。

## 设置 / Settings
模型设置支持原生文件选择、窗口、输出、Prefill、KV 精度、专家缓存、线程、显存比例及启动停止；原生 Cache 面板支持空闲重建及预算估算。Model settings include file dialogs, window, output, prefill, dtype, expert cache, threads, VRAM ratio and start/stop; the native cache panel provides idle rebuild and budget estimate. Local provider uses Anthropic Messages at the gateway root / 本地供应商使用 Messages 协议。

## 验证边界 / Verification boundaries
尚未运行完整 TypeScript 构建、Electron 或真实 GPU 测试。工具传输存在，执行链未验证；自动压缩实机和多模态待验证。No complete TypeScript build, Electron run or real GPU test verified. Tool transport exists; execution is unverified; end-to-end automatic compaction and multimodal remain unverified. Rebranding is partial: raster icons, installer identity, links, login and updater/telemetry require audit / 品牌、安装包、登录、更新与遥测仍需审计。不要运行上游发布脚本，不在未审计版本输入真实凭证 / Do not run upstream publishing scripts or enter real credentials before audit. Retain MIT notices / 保留 MIT 声明。

## 本地数据与自动记忆 / Local data and automatic context

用 `python desktop/launch_dev.py` 启动开发桌面。模型设置中的「打开本地数据目录」
可以查看应用管理的会话、附件、设置、日志和运行时缓存。默认目录为 Windows
`%LOCALAPPDATA%/Local-Longctx`、macOS `~/Library/Application Support/Local-Longctx`、
Linux `${XDG_DATA_HOME:-$HOME/.local/share}/Local-Longctx`。旧工作区里已有
Studio 数据时，继续使用旧目录。也可以在启动前设置 `LOCAL_LONGCTX_DATA_DIR`
来选择一个独立目录。备份或迁移前先关闭桌面和推理服务，再复制整个数据目录。模型权重、FreeToken 程序和
项目文件使用你选择的路径。

会话原文和压缩检查点存入本地会话历史。选用 Local-Longctx 预设后，应用会在历史
接近窗口时调用同一个本地模型压缩较早的内容，并在新一轮有余量时从该会话归档
自动找回相关原文。桌面使用无需自行请求受管会话 API。归档召回局限于当前会话。
桌面配置关闭 Harness 的自动会话日志上传和会话遥测。

Cache 面板中确认的容量会按模型、引擎文件、GPU 和启动配置保存。重启时用当前
原生缓存预算重新校验，恢复失败会在面板显示。保存的是 KV、MoE、SWA 和 GDN
容量方案。推理中的 KV 张量由 FreeToken 在运行时管理，经重启重新预填。

以前创建的本地供应商可能使用旧的临时密钥。首次升级后启动引擎，使用「复制本地
API 密钥」更新该供应商一次。之后本地网关会沿用当前数据目录保存的密钥。

The launcher owns a persistent desktop profile. Select the Local-Longctx preset
for automatic local compaction and within-session recall. The cache panel saves
approved capacities and revalidates them at startup. Live KV tensors are rebuilt
by the engine. Model weights and project files remain at their selected paths.
