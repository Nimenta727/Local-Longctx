# 远栈 FarStack 开发验收

远栈的首个目标平台是 Windows 11 x64 和 NVIDIA CUDA 13。当前代码仍处于集成验收阶段。公开的 alpha.5 是旧版源码预发行。

## 参数面板

模型运行后，缓存调度面板显示引擎提供的范围、步长和预计显存。轻量、日常对话、长程任务预设生成待应用配置。使用滑杆修改 KV、专家及模型实际提供的滑窗和状态池。查看总预算，空闲时点击应用。重置可撤销未应用的更改。

实验性 SSD 总开关默认关闭。内置引擎可以在 Auto KV 精度下启用活动 KV。选择 SSD 目录，调整显存常驻 Token、RAM 缓存与 SSD 文件上限后重启。默认使用运行数据目录的 `runtime-cache/active-kv`。活动 KV 模式与跨重启前缀检查点互斥，运行期间不支持重建缓存池。

## Windows 构建

在 Windows x64 的 Visual Studio 开发环境中准备 CPython 3.12 可搬移目录、CUDA 13、匹配的 NVIDIA 驱动和 Node.js 24。

```powershell
python desktop/build_windows_runtime.py C:\build\python C:\build\farstack-runtime
$env:FARSTACK_RUNTIME_DIR = 'C:\build\farstack-runtime'
npm ci --prefix desktop
npm --prefix desktop run package:win
```

该入口打包 `desktop/app` 和 FarStack 的内置运行时，输出 `desktop/dist/FarStack-*-Windows-x64.exe`。签名取决于 Windows 构建机的签名配置。发布前在 Windows NVIDIA 实机安装，验证选择 GGUF、启动引擎和生成。旧资料可通过 `LOCAL_LONGCTX_DATA_DIR` 指回原目录或完整备份。

## 功能验证

独立会话工作区将原文存到本地，借由会话标识进入网关预算检查。网关保存已收到的原文副本，再按原生 Token 预算缩减上下文。内容去重副本不作为累计 Token 统计。原文引用可通过已鉴权的 `POST /local/desktop/history/read` 读取。

活动 KV 报告磁盘读写故障时，网关会以显存 KV 重启引擎。若客户端尚未收到流内容，网关按恢复后的容量重新装配提示并重试一次。已开始返回的流不会自动重放，下一轮使用恢复后的引擎。用户保存的 SSD 配置保留，下次手动启动时会再次生效。

目前可在 CPU 上验证原文保留、完整工具调用组、混合 KV 的因果注意力和故障标记。真实累计百万 Token、Windows 原生运行和 SSD 满盘后的 GPU 生成仍需实机验收。
