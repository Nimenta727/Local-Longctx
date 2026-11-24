# 2026-11-24 — 预发行整理 / Source preview preparation

## 改动 / Changes
完整旧 main 保存到 research/v5.2-archive。精简 main，保留 FreeToken/Harness/ACE/缓存核心、验证与文档；移除旧 OpenClaw 及独立研究原型。统一版本 0.3.0a1，重写 README、使用、架构、测试、第三方与发行说明为双语；主要设置标签双语，保留英文协议标识及原版许可证。优化 JSON 检查、工具字段校验、缓存估算及预算溢出保护、CLI 入口、测试。 / Archive original main, remove obsolete OpenClaw and standalone research, retain core, tests and docs. Consistent version, bilingual documentation and main settings labels; preserve protocol identifiers and license text. Tighten JSON, tool field checks, cache estimates and budget, simplify CLI and add regressions.

## 验证限制 / Limits
当前容器无法解析 github.com，Node 版本不满足锁定上游要求，缺 pnpm、CUDA 实机；未运行完整仓库测试或构建。GitHub 连接不提供 Release/tag/附件写入操作，故只准备源码候选、分支与发布命令，不声称正式发布。 / No GitHub DNS, required Node/pnpm or CUDA; complete tests and builds not run. Connector lacks release/tag/asset creation; prepare source candidate and publishing instructions only.

## 下一步 / Next
执行源码检查与桌面编译；实机确认协议及 GUI、ACE 自动事务；在研究分支验证原生 KV 数据布局、CUDA/量化/稀疏/三级迁移；全面品牌与依赖审计后再发行独立桌面安装包。 / Run checks and build; validate protocol, GUI and ACE transaction; verify native KV research; complete branding and dependency audit before installer distribution.
