# CLI 与 API 指南 / CLI and API guide

桌面用户可以直接使用 Local-Longctx 模型预设。以下命令适用于独立运行网关和编写 API 客户端。 / Use the desktop preset for automatic context management, or follow this guide to run the gateway and build a direct API client. [桌面指南 / Desktop guide](../desktop/README.md)

## 启动本地网关 / Start the local gateway

1. 准备 Python 3.10+、匹配的 NVIDIA 驱动、可信 FreeToken 和兼容 MoE GGUF。
2. 复制 `configs/example.json` 为 `configs/config.local.json`。设置 FreeToken 和模型路径、已核实的模型上限与窗口预算。相对路径从配置文件目录解析。确认兼容后再把 `freetoken_model_verified` 设为 `true`。
3. 在启动网关的终端设置私有的 `LOCAL_LONGCTX_API_KEY`，再运行下列命令。

Prepare the engine and model, copy the example configuration, and set a private key in the gateway's environment. If no key is set, the CLI generates one and prints it locally.

```bash
python -m longctx --config configs/config.local.json hardware
python -m longctx --config configs/config.local.json plan
python -m longctx --config configs/config.local.json doctor
python -m longctx --config configs/config.local.json serve
```

## 接口与故障排查 / Endpoints and troubleshooting

默认地址为 `http://127.0.0.1:18080`，请求使用 Bearer 鉴权。

| 接口 / Endpoint | 用途 / Purpose |
| --- | --- |
| `GET /health` | 引擎健康状态 / Engine health |
| `POST /v1/messages` | 原生文本与工具协议 / Native text and tool transport |
| `POST /v1/messages/count_tokens` | 原生提示计数 / Native prompt count |
| `POST /v1/chat/completions` | OpenAI 风格的文本请求 / OpenAI-style text requests |
| `GET /local/cache/status` | 当前缓存容量及原生遥测 / Current cache capacities and telemetry |

超限错误会列出输入、输出、安全余量和窗口。显卡或内存不足时先用较小的兼容模型或窗口复查 `plan`。若 `doctor` 报告 `missing_flags`，检查已安装的 FreeToken 版本。启动失败时查看状态目录的 `freetoken.log`。 / Use the reported token breakdown to diagnose overflow. Check the plan and installed engine flags if startup fails.

## 受管会话行为 / Managed-session behavior

受管会话支持纯文本消息。压缩需要创建时授权，并显式预览、提交。可以在候选助手消息中用 `task_state` 标记原文的约束、决策、失败原因和待办。系统消息、用户消息、末尾四条消息与显式保护组会保留。对纯文本工具记录，可用 `"protected_groups": [[3, 4]]` 标出成组消息。

召回需要 SQLite FTS5。索引按需从原文构建，先匹配字面词，再补充本地中英工程概念。结果只来自所选版本的历史链。旧版本数据库未记录确切回滚目标时，召回可能在该点停止。指定版本仍可读取原文。响应里的 `sources` 给出原版本、消息索引和字符范围 `[start,end)`。召回只组装下一轮输入，调用方可另行追加实际问题和回复。

Direct clients use explicit compaction consent and commits. The recall endpoint returns a prompt and source ranges without adding a new session revision. SQLite FTS5 is required for retrieval. [架构 / Architecture](architecture.md)

<a id="managed-sessions"></a>

## 受管会话操作示例 / Managed session walkthrough

在同一终端设置 `LOCAL_LONGCTX_API_KEY` 并启动网关。以下 Bash 请求用
`curl`，以默认端口为例。 / Set the key, start the gateway, and use these
Bash examples against the default port.

```bash
post() {
  curl --fail-with-body -sS \
    -H "Authorization: Bearer ${LOCAL_LONGCTX_API_KEY}" \
    -H 'Content-Type: application/json' \
    --data-binary @- "http://127.0.0.1:18080$1"
}

post /local/session/create <<'JSON'
{"session":"demo","allow_semantic":true,"messages":[{"role":"user","content":"Keep the public API stable."}]}
JSON
```

1. 调用 `/local/session/append` 记录实际的用户与助手消息。每次传
   `session`、`expected_revision`、`expected_sha` 和新增的 `messages`。
   用最新响应里的 `revision`、`sha256` 填入并发校验字段。
   / Append actual user and assistant messages using the revision and SHA returned by the latest read or write.
2. 旧历史积累到需要压缩时，准备下方的 `compact.json`。示例中的索引、
   预算、估算值和遥测路径需要替换。索引从零开始，指定至少早于最后四条消息
   的助手消息，`quote` 必须出现在该消息原文中。遥测路径是 JSON 对象的键路径，
   对照实际运行的 FreeToken 版本填写。前两项取自引擎的 `/v1/cache/status`，
   后两项取自 `/v1/stats`。 / Replace the illustrative index, budgets, estimates and
   telemetry paths with values from your running engine and session.

```json
{
  "session": "demo",
  "expected_revision": 1,
  "expected_sha": "替换为当前响应的 sha256",
  "commit": false,
  "telemetry_profile": {
    "kv_used": ["kv", "used_pages"],
    "kv_capacity": ["kv", "total_pages"],
    "prefill_tps": ["throughput", "prefill_tps"],
    "active_requests": ["requests", "active"]
  },
  "estimates": {
    "growth_tokens_per_second": 60,
    "history_dependency": 0.2,
    "compact_seconds": 1,
    "expected_turns": 10,
    "prefix_recompute_tokens": 512,
    "cache_hit_fraction": 0.4,
    "seconds_since_compact": 600,
    "compact_peak_ram_gib": 0.1,
    "compact_peak_vram_gib": 0
  },
  "segments": [{
    "index": 1,
    "pinned": false,
    "anchors": [],
    "budget_chars": 512,
    "importance": 0.2,
    "access_frequency": 0.2,
    "dependency": 0.2,
    "task_state": [{"kind":"failed_attempt","quote":"Rejected v2 migration"}]
  }]
}
```

3. 执行 `post /local/session/compact < compact.json`。只有决策为
   `propose_semantic_compact` 且确认 `preview_messages` 可接受时，
   才改为 `"commit": true` 并重新提交。遇到 HTTP 409，先用
   `/local/session/read` 读取当前版本，再重新预览。
   / Inspect the preview, then explicitly commit. On a stale revision, read the current head and preview again.
4. 用下方请求生成下一轮消息。把响应的 `messages` 作为
   `/v1/chat/completions` 的消息数组，同时填写实际 `model`。
   推理后追加原始问题和回复。 / Send the returned messages to Chat Completions with the configured model ID, then append the original question and answer.

```bash
post /local/session/recall <<'JSON'
{"session":"demo","query":"What returned ERR_381 in decode_cache.py?","max_recall_tokens":384}
JSON
```

如需恢复历史，用 `/local/session/rollback` 提交 `session`、
当前 `expected_revision`、当前 `expected_sha` 和历史 `target_revision`。
成功后生成一个新版本。 / Restore an earlier revision with the current revision
and SHA plus the target revision. Rollback creates a new revision.
