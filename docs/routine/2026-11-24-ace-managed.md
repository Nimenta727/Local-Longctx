# 2026-11-24 — ACE managed execution preview

## 改动
- FreeToken 唯一后端保持不变；新增只读遥测采样，使用版本相关的显式字段路径，缺失时拒绝。
- 新增 SQLite 受管会话、原文版本归档、SHA256 校验、CAS 更新与回滚。
- 新增受管 compact API，结合六类指标做决策，使用确定性摘录、受保护字面量、整段重新计数与提交前空闲检查；默认只预览。
- 新增受管模块测试及接口文档。普通聊天请求不被静默改写。

## 验证与限制
本轮环境无法直接克隆 GitHub；代码和测试用例提交，未宣称实机 GPU/FreeToken 或完整单测通过。遥测 schema 需现场验证，任务评分/增长率等由调用者提供；未接入 OpenClaw 自动会话管理，未实现 KV 迁移、CUDA 稀疏内核、百万原生窗口。摘录仅保留字面锚点，不能保证语义保真。

## 下一步
固定 FreeToken 版本及模型并采集真实 JSON fixtures，校验 native tokenizer parity；执行单测和模拟重放；实现自动增长率、命中率与成本统计，接入 Agent 任务元数据、质量评估和用户可控自动 compact；在 GPU 空闲边界验证原生缓存调整，再推进 SSD KV 与 C++/CUDA 优化。
