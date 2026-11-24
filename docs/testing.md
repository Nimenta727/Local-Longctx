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
