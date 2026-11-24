# 2026-11-24 — Native 工具协议、ACE 会话接入与注意力参考算法

## 改动
- 新增本地 Anthropic Messages / count_tokens 代理，支持文本工具定义、工具调用与结果配对，保留 Harness 工具权限；GUI 本地供应商预设改为 Messages。
- 新增 ACE 只读 Harness 观察接口与固定上游源码 overlay，在原生压缩边界采集候选范围 token 数与真实硬件/KV 遥测。任务评分、成本及授权缺失时不自动压缩；本地 overflow 不静默截断。原生手动压缩保留。
- 新增分块 online softmax CPU 正确性参考、页面分数上界与近似路由参考及测试用例。
## 验证边界
未运行完整单测、Electron 编译或 GPU 联调；工具传输不等于实际工具执行已验证；自动 ACE 仍待任务元数据及授权接入；CPU 参考没有替换 FreeToken CUDA 内核。百万原生上下文未验证。
## 下一步
固定 FreeToken 版本，真实 Messages/SSE 与并行工具测试，核对模型模板及凭证；接入任务依赖/访问评分与成本统计，在 Harness 原生事务内实现经授权的自动 compact 和回放质量测试；验证注意力参考，接入真实 KV 数据布局、CUDA 内核、低比特量化及分页，再做 8K 至 1M 实机实验。
