# 验证 / Verification

## 源码检查 / Source checks

在仓库根目录运行以下命令。发行检查覆盖 Python 编译、单测和离线 ACE 规划。 / The source check covers Python compilation, unit tests, and offline ACE planning.

```bash
python scripts/check_release.py
python -m benchmarks.context_baseline --output baseline.json
```

## 离线上下文回放 / Offline context replay

固定用例覆盖早期约束、失败方案、工具记录、分散证据和跨语言改写。三个变体使用同一历史与末轮问题。受限变体共用预算，受管会话中有部分由调用方预先标记的任务状态。离线计数来自 UTF-8 字节估算。

| 提示构造 / Prompt variant | 进入提示的关键证据 / Evidence included |
| --- | ---: |
| 完整历史 / Full history | 9/9 |
| 滑动窗口 / Sliding window | 0/9 |
| 受管会话 / Managed session | 9/9 |

受管会话在这组固定用例中从 8/9 提升至 9/9，新增命中是用英文恢复问题找回中文备份记录。该表反映 Python 受管会话的证据可见性。模型答对率、桌面端到端和 GPU 指标需要各自测量。 / This synthetic benchmark measures evidence visibility in managed-session prompts. Model quality, desktop flows, and GPU metrics have separate validation steps.

## Harness 源码回归 / Harness source regression

按桌面指南固定上游 checkout 并安装依赖。从 `desktop/upstream` 运行核心测试。 / With the pinned overlay and dependencies prepared, run the focused suite from `desktop/upstream`.

```bash
pnpm exec vitest run \
  apps/desktop/tests/local-longctx-ipc.spec.ts \
  packages/compaction/compaction-basic/tests/compaction-basic.spec.ts \
  packages/compaction/compaction-basic/tests/local-memory.spec.ts \
  packages/spill/spill-policy/tests/spill-policy.spec.ts \
  packages/spill/spill-policy/tests/local-tool-evidence.spec.ts \
  packages/core/agent-loop/tests/loop.spec.ts
```

测试覆盖就绪进程归属、请求预算、会话压缩与回放、任务状态出处、跨语言召回、工具输出归档和回读。 / Tests cover worker readiness, prompt budgeting, durable checkpoints, recall, and tool-result spill.

## NVIDIA 实机 / NVIDIA runtime

启动网关并设置 `LOCAL_LONGCTX_API_KEY`，以实际网关窗口替换示例值。

```bash
python benchmarks/native_tool_smoke.py
python -m benchmarks.context_baseline --live --engine-window 8192 --output live-baseline.json
```

工具冒烟脚本验证协议配对，使用无副作用的 echo 数据。实机基线使用原生 Messages 计数和生成，报告 JSON 字段准确性、首个文本 Token 延迟、引擎返回的用量和采样 KV 页峰值。超出实际窗口的完整历史会标记为跳过。短请求可能未采到峰值。比较时保持模型、量化、预算和历史规模一致。

自备提示可用 `python benchmarks/managed_replay.py replay.json`。输入包含 `full`、`extract`、`recall` 三组消息和 `expected` 字段，支持 `--order` 和 `--warm-prefix`。

桌面端到端验收还包括 Electron 启动、工具权限、空闲缓存重建、进程退出与重启恢复。 / Desktop validation still requires a full Electron run, tool permissions, idle cache rebuild, and restart recovery. [桌面构建 / Desktop build](../desktop/README.md)
