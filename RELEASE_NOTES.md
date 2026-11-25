# Local-Longctx Studio v0.3.0-alpha.4

源码预发行 / Source prerelease · Python 3.10+ · Apache-2.0

## 本版更新 / What's new

- **Harness 请求预算**。发送前估算新消息、系统提示与工具定义。引擎对完整原生 Messages 请求计数，超限错误列出实际预算明细。
- **长工具结果归档**。大型文本可保存到本地，模型看到首尾、预算内的原始错误行和全文路径。
- **带出处的任务状态与中英召回**。检查点可保留原文里的约束、决策、失败原因和待办。检索优先字面命中，再用本地中英工程术语补充。
- **稳定性**。并发写入共享版本保护，事务异常时回滚并关闭连接。损坏缓存方案可通过重新应用修复，恢复成功以原生容量复核为准。桌面只接受本次启动的工作进程就绪，网关拒绝格式错误的引擎响应。

This release adds unified request budgeting, local archives for large tool outputs, source-linked task state, and bilingual recall. It also hardens session transactions, cache restoration, worker readiness, and gateway response handling.

## 使用与升级 / Getting started and upgrading

1. 从发行页下载源码，或检出 `v0.3.0-alpha.4`。运行 `python -m longctx --version` 应显示 `0.3.0a4`。
2. 桌面用户准备一份新的固定 Harness 覆盖层，然后构建并运行 `python desktop/launch_dev.py`。在模型设置中启动引擎并选择 Local-Longctx 预设。 [桌面构建和启动 / Desktop setup](https://github.com/Nimenta727/Local-Longctx/blob/v0.3.0-alpha.4/desktop/README.md)
3. 如果旧数据位于旧 checkout，先退出桌面和推理服务，再把 `LOCAL_LONGCTX_DATA_DIR` 指向原目录或其完整备份。直接调用网关的客户端可继续读取和写入旧受管会话，检索索引会按需从原文重建。 [CLI 与 API 指南 / CLI and API guide](https://github.com/Nimenta727/Local-Longctx/blob/v0.3.0-alpha.4/docs/usage.md)

Download or check out this tag, prepare a fresh desktop overlay, and select the Local-Longctx preset. Point `LOCAL_LONGCTX_DATA_DIR` to the previous data directory or a full copy when migrating between checkouts.

## 验证范围 / Verification

38 项 Python 测试、245 项 Harness 与桌面相关测试及涉及模块的 TypeScript 检查通过。固定离线回放中，受管会话的证据覆盖从 8/9 提升至 9/9。完整 Electron 运行、GPU 性能和模型任务完成率仍待实测。本版提供源码归档。 / 38 Python tests, 245 focused Harness and desktop tests, and TypeScript checks passed. The offline fixture recovered 9 of 9 evidence items. Full Electron, GPU, and model-quality measurements remain pending. [验证方法 / Verification](https://github.com/Nimenta727/Local-Longctx/blob/v0.3.0-alpha.4/docs/testing.md)
