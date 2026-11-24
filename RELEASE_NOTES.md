# Local-Longctx Studio v0.3.0-alpha.2

源码预发行 / Source prerelease · Python 3.10+ · Apache-2.0

## 更新 / What changed

- 压缩可保留调用方标记的约束、决策、失败原因和待办，并附原始版本与消息索引。可成组保留文本工具调用与结果。 / Compaction preserves caller-marked constraints, decisions, failed attempts and todos with source references. Related text tool messages can be protected as a group.
- 新增 `POST /local/session/recall`。SQLite FTS5 可按文件名、错误码或中文关键词找回归档片段，按后端计数控制额外 Token，并遵循当前版本的历史链。 / Recall retrieves archived excerpts using SQLite FTS5, the engine's token counts and the selected session revision's history.
- 当前缀缓存命中率高且窗口有余量时，ACE 可延后压缩。 / ACE can defer compaction while the prefix is warm and the context window has room.

## 使用 / How to use

1. 从发行页下载源码并解压，或检出 `v0.3.0-alpha.2`。在源码目录运行 `python -m longctx --version`，应显示 `0.3.0a2`。 / Download and extract the release source or check out the tag, then verify the Python version string from the source directory.
2. 运行模型需要 NVIDIA GPU、兼容的 FreeToken 可执行文件及 MoE GGUF。复制 `configs/example.json` 为 `configs/config.local.json`，填写引擎和模型路径及窗口预算，确认兼容后设置 `freetoken_model_verified`。使用 SQLite FTS5 的 Python 环境才能检索归档。 / Configure the NVIDIA FreeToken engine and compatible MoE GGUF. Recall requires a Python build with SQLite FTS5.
3. 在同一终端设置私有的 `LOCAL_LONGCTX_API_KEY`，依次运行下面的诊断和启动命令。 / Set a private API key in the same shell, then diagnose and start the gateway.

   ```bash
   python -m longctx --config configs/config.local.json doctor
   python -m longctx --config configs/config.local.json serve
   ```

4. 用 Bearer 密钥访问默认的 `http://127.0.0.1:18080`。创建允许语义压缩的受管会话，先预览再显式提交压缩。下一轮调用 `/local/session/recall`，把返回的 `messages` 送给 `/v1/chat/completions`。完整请求、追加与回滚见操作示例。 / Use the Bearer key on the loopback gateway. Create a managed session with compaction consent, preview and commit explicitly, then send recalled messages to Chat Completions. [受管会话操作示例 / Managed session walkthrough](https://github.com/Nimenta727/Local-Longctx/blob/v0.3.0-alpha.2/docs/usage.md#managed-sessions)

## 验证范围 / Verification

源码检查和 30 项测试通过。离线回放验证了任务状态保留、预算内检索和回滚行为。真实 GPU、桌面构建、端到端工具执行及百万 Token 原生窗口尚未验证。本版发布源码归档，无安装包。 / Source checks and 30 tests passed. Offline replay covered state retention, recall budgeting and rollback. GPU performance, desktop builds, end-to-end tools and a native million-token window remain unverified. Source archives only.
