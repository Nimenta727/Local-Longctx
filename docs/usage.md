# 使用指南 / User guide

## 1. 环境 / Requirements
Python 3.10+；NVIDIA Windows/Linux 目标平台；可信 FreeToken 程序和匹配的 MoE GGUF。硬件、驱动和模型兼容性参见 [FreeToken 官方项目 / upstream](https://github.com/FlashML-org/FreeToken)。当前不是已验证的跨平台产品。Python 3.10+, NVIDIA Windows/Linux target, trusted FreeToken and compatible MoE GGUF. Check upstream compatibility. Cross-platform operation is unverified.

## 2. 桌面 / Desktop
按 [桌面说明 / Desktop instructions](../desktop/README.md) 准备上游源码。在模型设置选择引擎、GGUF、模型上限、原生窗口（先 8K）、输出预算、KV 精度、专家槽、线程和显存比例。启动后使用本地模型供应商预设。Prepare pinned sources; in Models choose the executable, GGUF, model limit, initial 8K native window, output reserve, KV dtype, expert slots, threads and VRAM ratio. Start and select the local provider preset. Existing provider credentials may need updating after restarting.

Cache 面板显示原生缓存几何、当前容量、预算和吞吐量；空闲时经确认应用调整。Live Cache panel shows native geometry, capacity, budget and throughput; changes require an idle engine and confirmation. Live values are not saved across restart / 实时调整重启不保留。

## 3. CLI（开发诊断 / Developer diagnostics）
将 configs/example.json 复制为 configs/config.local.json；相对路径基于配置目录。修改路径、实际模型上限，只有确认兼容后才将 freetoken_model_verified 设为 true。Copy the example config, resolve paths relative to it and verify the installed engine/model before setting the compatibility flag.

```bash
python -m longctx --config configs/config.local.json hardware
python -m longctx --config configs/config.local.json plan
python -m longctx --config configs/config.local.json doctor
python -m longctx --config configs/config.local.json serve
```

默认本地 API 根为 http://127.0.0.1:18080；Messages 使用 /v1/messages，OpenAI 文本使用 /v1/chat/completions。密钥为 LOCAL_LONGCTX_API_KEY 或 CLI 随机生成的私有密钥；不得共享或提交。Default loopback base above; use Messages or plain-text Chat Completions, keep the session key private. Native text and tool transport is experimental, images unsupported.

## 4. ACE
`python -m longctx compact-plan configs/compact.example.json` 离线测试决策，不启动 GPU、不修改对话。Offline policy evaluation without GPU or history mutation. Harness observer reads telemetry; the managed-session API is a separate explicit workflow. See [architecture](architecture.md).

## 5. 故障 / Troubleshooting
- no eligible NVIDIA GPU: 检查驱动及空闲显存 / inspect driver and free VRAM.
- insufficient RAM: 保守预算未通过，尝试较小模型 / choose a smaller compatible model.
- missing_flags: 当前引擎 CLI 不匹配 / inspect installed FreeToken version.
- context budget exceeded: 缩短输入，检查真实模型和缓存容量 / reduce input and verify window and pools.
- worker exited: 查看本地 desktop-worker.log 与 freetoken.log，分享前去除隐私信息 / inspect local logs and redact before sharing.

## 受管会话的任务状态与归档检索

继续用 `POST /local/session/compact` 预览和显式提交。每个候选段可加
`"task_state": [{"kind":"failed_attempt","quote":"Rejected v2 migration"}]`。
类别包括 `constraint`、`decision`、`failed_attempt` 和 `todo`。
`quote` 由调用方提供，必须命中该段中的一行原文。压缩保留整行，并附
`revision:index` 来源。预算放不下标记和必保行时，预览报错并保留原版本。
原有的 system、user 和末尾四条消息保护继续适用。对于已经作为纯文本存入
受管会话的工具调用和结果，可传 `"protected_groups": [[3, 4]]`，
把这一组原样保留。原生 Messages 的结构化工具内容仍由 Harness 管理。

提交后可用以下请求准备下一轮：

```http
POST /local/session/recall
Content-Type: application/json

{"session":"demo","query":"What returned ERR_381 in decode_cache.py?","max_recall_tokens":384}
```

默认使用当前版本，也可指定 `revision`。返回的 `messages` 可提交给
`/v1/chat/completions`。搜索结果作为引用资料附在末尾的新用户消息里，
已有消息保持原样。返回的 `sources` 标明原版本、消息索引和字符范围
`[start,end)`。检索预算使用后端提示计数，且受上下文上限和输出预留约束。
这个准备请求不追加会话消息。完成推理后，可用返回的版本和 SHA 追加实际
用户请求及模型回复。

SQLite 需支持 FTS5。首次检索按需为已有压缩版本建立索引。检索沿恢复后的
版本链进行。对于升级前创建、且数据库未记录确切回滚目标的回滚点，
检索可能在该点停止。原文仍可通过指定版本读取。

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
