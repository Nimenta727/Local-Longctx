# 更新日志 / Changelog

## 0.3.0-alpha.2 — 2026-11-24
- 保留任务状态及来源，支持成组保护文本工具记录。 / Preserve task state and source references, with optional protection for related tool messages.
- 新增预算内归档检索，按会话版本链恢复原文。 / Retrieve archived excerpts within a token budget and the selected revision's history.
- 有缓存余量时延后压缩，增加三种上下文的对照回放。 / Defer compaction when the prefix is warm and there is headroom, and compare three prompt variants in replay.

## 0.3.0-alpha.1 — 2026-11-24 (candidate / 候选)
FreeToken gateway, Harness overlay and explicit ACE managed sessions. / FreeToken 网关、Harness 桌面覆盖与显式 ACE 受管会话。

## Earlier previews / 历史版本
0.1: bootstrap and local API / 初始服务。
0.2: FreeToken-only, ACE, managed sessions / 单后端及压缩会话。
V4–V5.2: Harness overlay, Messages, cache workbench and separate research prototypes / 桌面覆盖、工具协议及缓存研究。
