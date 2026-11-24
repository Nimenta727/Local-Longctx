# 2026-11-24 — Harness 桌面源码集成预览

## 改动
- 固定 DeepSeek Harness 0.2.3-alpha.2 / 4b399c39a6d1479cd84ca591b4d7c88e24d38a96，采用可重复源码 overlay，不重写前端、不删除原有工具插件。
- 模型设置加入本地模型面板：原生文件选择、窗口/输出/线程/显存比例/KV 格式、启动停止、连接状态及本地 provider 预设。
- Electron 主进程只允许原有主窗口的受信 IPC；选择可信可执行程序需本地确认；使用父进程 EOF 监督 Python worker，保持本地 API 鉴权。
- 替换桌面打包产品名与原创 SVG 矢量标志，保留上游 MIT 与版权。暂不发行。
## 验证边界
源码 overlay 尚未在真实 checkout 应用或 TypeScript 编译；GPU、Electron、Harness 工具调用与多模态未联调。上游工具代码保留但本地后端暂不支持 tool calls。旧 provider 密钥更新仍需 GUI 手动编辑。自动 ACE 尚未接入；原生百万上下文未验证。品牌残余、签名、更新通道、网络/遥测需审计。
## 下一步
先运行锁定版本 overlay、编译并测试 Electron/IPC/进程退出，验证 FreeToken 模板及本地聊天；完成模型发现与密钥轮换；接入 Harness 原生 tool-call schema 和 ACE 生命周期，保留权限机制；接入多模态及硬件实时界面；全面替换用户可见商标并独立发行标识、更新通道、第三方许可审查。
