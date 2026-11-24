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
