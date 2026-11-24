# 验证 / Verification

## Core / 核心
```bash
python -m compileall -q longctx desktop benchmarks tests
python -m unittest discover -s tests -v
python -m longctx compact-plan configs/compact.example.json
```
测试覆盖配置、硬件决策、前缀身份、ACE 策略、受管会话、缓存预算、Messages 与版本一致性。Tests cover configuration, scheduling, prefix identity, ACE, managed sessions, cache budgets, Messages and release consistency. 新测试未在此次环境执行 / New tests were not executed in this environment.

## Integration / 联调
先安装锁定 Harness 依赖并运行 `python desktop/verify_build.py`，再实际启动桌面。On an NVIDIA machine, run an authenticated local engine and `python benchmarks/native_tool_smoke.py`; the script uses harmless echo data without executing real tools. Verify SSE, native tool pairing, GUI, process shutdown, cache apply and permission controls. 实机验证 SSE、工具结果配对、权限、GUI、退出与缓存重建。Do not input secrets into unaudited builds / 未审计版本不输入真实凭证。

## Release gate / 发行门槛
Source preview must pass compile/unit tests before publishing. A stable desktop release also requires Windows/Linux GPU tests, full brand and upstream license audit, SBOM, installer signing and independent end-to-end checks. 源码预发行先通过编译和单测；桌面正式发行还需实机、品牌授权、SBOM、签名与端到端验收。No claimed test pass or 1M measurement / 不声称已通过未执行的测试或百万实测。

## Managed context replay / 受管上下文回放

`tests/test_managed.py` 用同一份历史对比完整上下文、原摘录和任务状态加
归档检索，验证早期约束、失败原因、工具错误记录的可见性及预算、回滚行为。
离线用例采用模拟计数。

实机可用 `python benchmarks/managed_replay.py replay.json`。输入 JSON 有
`full`、`extract`、`recall` 三个消息数组，分别使用相同历史的完整版本、
无任务状态的压缩预览和启用任务状态后由 recall API 返回的消息。三个变体
使用同一条末轮问题，要求模型输出 JSON。另加 `expected` 对象，逐字段
定义应遵守的约束、应跳过的失败方案和应找回的工具结果。脚本使用本地
`LOCAL_LONGCTX_API_KEY`，报告逐字段准确性、首 Token 延迟和采样到的
KV 页峰值。短请求可能采不到峰值。可用 `--order` 调整顺序，区分先后
顺序带来的缓存影响。用 `--warm-prefix` 可在每个变体前发送完整历史前缀预热，
用于测量历史重写后的首轮延迟。
