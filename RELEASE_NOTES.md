# Local-Longctx Studio v0.3.0-alpha.3

源码预发行 / Source prerelease · Python 3.10+ · Apache-2.0

## 桌面版更新 / Desktop changes

- 选择 Local-Longctx 本地模型后，桌面会自动保存会话。历史接近窗口上限时，本地模型会压缩较早的内容。后续轮次有余量时，桌面可从当前会话找回相关原文和工具结果，无需手动调用记忆 API。 / The local model preset automatically saves, compacts and retrieves relevant excerpts from the current session.
- 在 Cache 面板确认的 KV、MoE、SWA 和 GDN 容量设置会按模型、引擎、GPU 和启动配置保存。重启时使用原生引擎预算重新校验，推理中的缓存张量由 FreeToken 重建。 / Approved cache capacity settings are saved and revalidated at startup. FreeToken rebuilds live cache tensors.
- 会话、附件、设置、日志和运行时缓存放在应用数据目录。默认关闭会话日志上传和会话遥测。 / The application data directory holds sessions, attachments, settings, logs and runtime caches. Automatic session-log upload and session telemetry are disabled by default.

## 使用与升级 / Getting started and upgrading

1. 下载下面的源码，或检出 `v0.3.0-alpha.3`。运行 `python -m longctx --version`，应显示 `0.3.0a3`。 / Download the source or check out the tag and verify the version.
2. 桌面预览需要兼容的 NVIDIA GPU、FreeToken 和 MoE GGUF，以及固定版本的 Node.js、pnpm 和 Harness 构建依赖。按桌面指南准备源码和依赖，再运行 `python desktop/launch_dev.py`。升级时请从新版本源码重新准备桌面覆盖层。 / Prepare the pinned desktop sources and dependencies, then launch the development app. Prepare a fresh overlay when upgrading. [桌面构建与使用 / Desktop setup](https://github.com/Nimenta727/Local-Longctx/blob/v0.3.0-alpha.3/desktop/README.md)
3. 在模型设置中选择引擎和模型，启动引擎并选择 Local-Longctx 本地模型预设。若旧配置使用临时密钥，升级后通过「复制本地 API 密钥」更新一次供应商配置。 / Start the configured local engine and select the Local-Longctx preset. Update a legacy provider credential once if it used an old temporary key.
4. 在模型设置点击「打开本地数据目录」查看文件。备份或迁移时，先退出桌面和推理服务，再复制整个目录。如果旧版数据在原源码目录下，换到新源码目录时，可在启动前把 `LOCAL_LONGCTX_DATA_DIR` 指向原数据目录或其完整副本。 / Open the data folder from model settings. Shut down before copying the folder for backup or migration. When moving to a new source checkout, set `LOCAL_LONGCTX_DATA_DIR` to the old profile or its complete copy if it was stored inside the old checkout.

直接调用网关的客户端仍可使用受管会话 API。 / Direct gateway clients can continue using the managed-session API. [API 指南 / API guide](https://github.com/Nimenta727/Local-Longctx/blob/v0.3.0-alpha.3/docs/usage.md#managed-sessions)

## 验证 / Verification

32 项 Python 测试、140 项相关桌面测试及 TypeScript 检查通过。真实 GPU 上的自动压缩、缓存恢复和完整 Electron 运行仍待验证。此版本提供源码归档。 / 32 Python tests, 140 relevant desktop-side tests and TypeScript checks passed. Real-GPU compaction, cache restoration and a complete Electron run remain unverified. Source archives only.
