# 2026-11-24 — 多后端与自研管理层

改动：新增 FreeToken 实验适配、硬件检测与启动前选型、独立 token 预算及前缀身份校验；新增实验配置和单元测试；更新 README 与 V2.1 架构。保留 llama.cpp 兼容路线及 OpenClaw UI 接入。

验证：源码提交，未执行本地单元测试或 GPU/FreeToken 实测。当前无 SSD tensor cache、跨引擎状态迁移、注意力内核或动态重新分配，不能称为已实现百万 token。FreeToken token 估算与真实模板需要验证。

下一步：锁定上游版本并联调；采集真实缓存/显存指标与带宽；验证 checkpoint export/restore 后实现冷热存储；按上下文梯度验证性能与准确性；独立品牌发行。
