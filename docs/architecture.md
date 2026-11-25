# 架构 / Architecture

## 请求路径 / Request path

`Harness 桌面与 Agent → 具备鉴权的本地网关 → FreeToken → NVIDIA GPU`

Harness 管理界面、工具权限和会话事务。网关负责请求校验、原生 Token 计数、引擎生命周期和缓存控制。FreeToken 执行推理。原生 Messages 在转发前对系统提示、历史、工具定义和工具结果整体计数，并留出请求的输出预算和 256 Token 余量。文本 Chat Completions 使用跨协议计数估算。

Harness owns tool permissions and session transactions. The gateway validates requests and controls FreeToken. Native Messages measures the full prompt using the engine tokenizer. Chat Completions uses a cross-protocol estimate.

## 桌面上下文 / Desktop context

1. Harness 用当前会话、即将加入的消息、系统提示增量、工具定义和输出预留估算压力。接近阈值时优先处理可缩减的工具结果。
2. 压力仍高时，本地模型在保持工具调用与结果配对的历史范围上生成检查点。检查点可附上有事件序号的任务原文摘录，只在替换后仍能缩短上下文时写入。
3. 后续轮次有余量时，桌面从当前会话前驱归档检索。文件名和错误码优先，中英术语匹配补充召回。新消息与历史摘录一同送入最终计数。
4. 大型文本工具结果可保存到本地 spill 文件，提示中保留预览和读取路径。已有原文和会话历史由本地存储保管。

The desktop budgets the next request, reduces large tool results, compacts balanced spans, and uses available headroom for source-linked recall. Cache state belongs to the engine. Persisted conversation facts belong to the session.

## 受管会话 API / Managed sessions

直接使用网关的客户端可以创建独立的 SQLite 受管会话。压缩由调用方预览并显式提交。提交使用版本号和 SHA 校验，原始消息留在历史版本，回滚生成新版本。召回只沿所选版本的历史链检索，FTS5 先匹配字面词，再补充概念命中。索引从原文按需重建。归档存于应用数据目录，使用文件系统权限保护。

这一路径的 ACE 决策结合窗口、KV、内存和显存压力、增长率、任务依赖及前缀重算代价。它与桌面 Harness 的自动检查点是两个入口。 / Direct clients can explicitly preview, commit, recall, and roll back SQLite revisions. The managed ACE policy also considers resource pressure and replay cost. [请求示例 / API examples](usage.md#managed-sessions)

## 缓存与历史长度 / Cache and history length

`GET /local/cache/status` 返回当前缓存池容量、步长和预算。`POST /local/cache/apply` 需要当前配置版本、显式确认和空闲引擎。应用后的容量按模型、引擎文件、GPU 和启动参数保存，恢复时重新校验并读取实际分配值。推理中的缓存页由引擎重建。

**归档长度、单轮原生窗口和实际 KV 容量分别衡量。** 百万 Token 是逻辑历史研发目标。CUDA 注意力、量化 KV 和 RAM/SSD 分层存储实验保留在研究分支。 / Archive length, native window, and KV capacity are separate measurements. The million-token logical-history target is a research goal. [研究分支 / Research archive](https://github.com/Nimenta727/Local-Longctx/tree/research/v5.2-archive)
