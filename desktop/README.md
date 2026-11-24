# Local-Longctx Studio — 桌面源码预览 / Desktop source preview

采用固定 DeepSeek Harness 源码覆盖层，不复制整套上游仓库，不删除原有工具、权限及沙箱。不是安装包。Pinned source overlay, not a bundled installer. Upstream tools, permission checks and sandbox remain intact.

## 开发准备 / Developer setup
1. 核对 [harness.lock.json](harness.lock.json) 中固定修订及上游 MIT 许可 / Review the pinned revision and upstream MIT license.
2. 执行 `python desktop/prepare_harness.py`。脚本不覆盖现有 checkout，锚点变化时停止 / Prepare a fresh checkout; stop on mismatched anchors.
3. 安装上游要求的 Node.js ^24.22.3 或 >=26.13.1、pnpm 11.28.5，并按照上游说明安装锁定依赖与原生工具链 / Install upstream-required Node/pnpm and native dependencies following upstream instructions.
4. 执行 `python desktop/verify_build.py`，然后 `python desktop/launch_dev.py` / Run build verification, then launch the development GUI. Do not use upstream publish targets / 不使用上游发行命令。

## 设置 / Settings
模型设置支持原生文件选择、窗口、输出、Prefill、KV 精度、专家缓存、线程、显存比例及启动停止；原生 Cache 面板支持空闲重建及预算估算。Model settings include file dialogs, window, output, prefill, dtype, expert cache, threads, VRAM ratio and start/stop; the native cache panel provides idle rebuild and budget estimate. Local provider uses Anthropic Messages at the gateway root / 本地供应商使用 Messages 协议。每次重启可能需要更新供应商密钥 / A restart may require updating the provider credential.

## 验证边界 / Verification boundaries
尚未运行完整 TypeScript 构建、Electron 或真实 GPU 测试。工具传输存在，执行链未验证；ACE 自动事务与多模态待接入。No complete TypeScript build, Electron run or real GPU test verified. Tool transport exists; execution is unverified; automatic ACE and multimodal remain open. Rebranding is partial: raster icons, installer identity, links, login and updater/telemetry require audit / 品牌、安装包、登录、更新与遥测仍需审计。不要运行上游发布脚本，不在未审计版本输入真实凭证 / Do not run upstream publishing scripts or enter real credentials before audit. Retain MIT notices / 保留 MIT 声明。
