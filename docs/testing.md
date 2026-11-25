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

## SSD 专家读取原型 / SSD expert read prototype

从源码目录安装可选 GGUF 读取依赖后，使用单文件、小端的 Qwen3 MoE GGUF。
原型已覆盖官方 Qwen3-30B-A3B Q4_K_M 中的 Q4_K 和 Q6_K 专家张量。

```bash
python -m pip install '.[ssd-research]'
python -m benchmarks.ssd_experts /path/to/Qwen3-30B-A3B-Q4_K_M.gguf \
  --expert 0:0 --expert 0:127 --staging-mib 4 --verify
```

原型索引张量偏移量，并按专家读入一块可复用缓冲区。`--verify` 会另外用 GGUF
映射视图比较原始字节。读取耗时可能包含操作系统文件缓存的影响。

### FreeToken 专家换入实验

补丁针对 FreeToken `94938a6a576926d384986fbe8cd7f1a4eb6d687e`。在支持
FreeToken 的 NVIDIA GPU 环境中，准备一份专用的 FreeToken 工作树，并在同一个
Python 环境安装两个项目。将下面的本地源码路径和模型路径替换为实际路径。

```bash
LOCAL_LONGCTX=/path/to/Local-Longctx
MODEL=/path/to/Qwen3-30B-A3B-Q4_K_M.gguf
git clone https://github.com/FlashML-org/FreeToken.git FreeToken-ssd
cd FreeToken-ssd
git checkout --detach 94938a6a576926d384986fbe8cd7f1a4eb6d687e
git apply --check "$LOCAL_LONGCTX/experiments/freetoken_ssd/freetoken.patch"
git apply "$LOCAL_LONGCTX/experiments/freetoken_ssd/freetoken.patch"
uv venv
source .venv/bin/activate
uv pip install -e '.[accel]' -e "${LOCAL_LONGCTX}[ssd-research]"

ft serve --model "$MODEL" --gpu 0 --experimental-ssd-experts \
  --moe-strategy offload --max-running-requests 1 --cuda-graph-max-bs 0 \
  --disable-moe-prefill-overlap --moe-cache-size 256 --num-tokens 2048 \
  --max-seq-len-override 1024 --cache-type naive
```

启动日志应出现 `Experimental SSD experts enabled`。实验使用 GPU 专家槽和
一块至多 4 MiB 的锁页暂存区。解码只读未命中的专家，预填沿用 FreeToken 的
整层暂存布局，首次预填可能读过大部分专家权重。GGUF 文件须在运行期间保持不变。
桌面 Harness 可选同一份打过补丁的程序，再在「启动参数」打开实验性 SSD 总开关并启用专家权重。单独运行 FreeToken 时可通过 `--experimental-ssd-expert-staging-mib` 调整单专家锁页暂存上限。

GPU 验收时，用同一完整 GGUF 和相同参数顺序跑两次，只切换
`--experimental-ssd-experts`。用相同提示、温度 `0` 和生成上限比较
生成结果、首 Token 延迟、解码速度和进程峰值 RSS，同时记录系统可回收文件缓存。
再把专家数据大于可用 RAM 的场景单独跑一次，确认能完成预填和生成。CPU 字节
校验无法确认这些 GPU 结果。

### SSD KV 前缀检查点实验

使用上面同一份 FreeToken 补丁。通过桌面「启动参数」打开实验性 SSD 总开关并勾选「保存 KV 前缀检查点」，或在 Local-Longctx JSON 配置中同时设置 `"experimental_ssd": true` 和 `"ssd_kv_checkpoint": true`。单独运行 FreeToken 时，使用 `--experimental-ssd-kv /path/on/ssd/ssd-kv.bin`，可附加 `--experimental-ssd-kv-limit-mib` 调整文件上限。使用 `--cache-type radix --max-running-requests 1 --kv-cache-dtype auto`、单 GPU 和 BF16。若沿用上一节命令，请将 `--cache-type naive` 改为 `--cache-type radix`。总开关启用后，两项功能可独立选择。

Local-Longctx 管理的文件位于 `state_dir/runtime-cache/ssd-kv.bin`。如需使用 SSD，请将本地数据目录放在 SSD 上。每个数据目录保留最近一份可复用的提示前缀，文件上限默认 256 MiB，可调范围为 16–1024 MiB。调低上限后，超限的旧检查点不会恢复，下次成功写入时会替换它。写入期间会有一份临时文件。检查点与提示内容相关，应像聊天记录一样保管。关闭开关会停止使用该文件。要清除它，可停止引擎后删除该文件。启用时，FreeToken 原生清缓存操作也会删除它。

GPU 验收时，发送一条只生成少量 token 的固定提示，确认请求结束后写出了文件。重启引擎并发送相同提示，比较生成结果、`usage.prompt_tokens_details.cached_tokens` 和首 Token 延迟。然后更改前缀或关闭开关，确认重启后从头预填。活动 KV 仍由显存池承载，检查点恢复也需要足够的可用显存页。
