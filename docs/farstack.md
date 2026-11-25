# 远栈 FarStack 开发验收

远栈的首个目标平台是 Windows 11 x64 和 NVIDIA CUDA 13。当前代码仍处于集成验收阶段。公开的 alpha.5 是旧版源码预发行。

## 参数面板

模型运行后，缓存调度面板显示引擎提供的范围、步长和预计显存。轻量、日常对话、长程任务预设生成待应用配置。使用滑杆修改 KV、专家及模型实际提供的滑窗和状态池。查看总预算，空闲时点击应用。重置可撤销未应用的更改。

实验性 SSD 总开关默认关闭。内置引擎可以在 Auto KV 精度下启用活动 KV。选择 SSD 目录，调整显存常驻 Token、RAM 缓存与 SSD 文件上限后重启。默认使用运行数据目录的 `runtime-cache/active-kv`。活动 KV 模式与跨重启前缀检查点互斥，运行期间不支持重建缓存池。

## Windows 构建

在 Windows x64 的 Visual Studio 开发环境中准备 CPython 3.12 可搬移目录、CUDA 13 和匹配的 NVIDIA 驱动。使用仓库固定的 Node 和 pnpm 版本。

```powershell
python desktop/build_windows_runtime.py C:\build\python C:\build\farstack-runtime
$env:FARSTACK_RUNTIME_DIR = 'C:\build\farstack-runtime'
python desktop/prepare_harness.py
Set-Location desktop/upstream
pnpm install --frozen-lockfile
pnpm run build:artifacts
pnpm --filter @deepseek-ai/dsh-desktop run package:win:x64:unsigned
```

上述命令为未签名的 NSIS 安装程序构建入口，输出目录是 `desktop/upstream/apps/desktop/.desktop-build/targets/win-x64/unsigned-artifacts`。包内检查使用安装目录自带的 Python 验证 CUDA 版 PyTorch、FreeToken 原生扩展和命令入口。还需要在 Windows NVIDIA 实机安装、选择模型并完成一次生成。发行时上传通过验收的 `farstack-*-win-x64-unsigned.exe`，并标明签名状态。

远栈随包使用自己的 Python 和 FreeToken，旧开发模式仍可选外部引擎。打包态跳过上游账号登录页，模型就绪后自动注册远栈本地模型。旧数据可通过 `LOCAL_LONGCTX_DATA_DIR` 指回旧数据目录或其完整备份。

## 功能验证

桌面本地模型借由会话标识进入预算检查。网关保存已收到的原文副本，再按原生 Token 预算缩减上下文。既有 Harness 会话日志保留原始事件，网关的内容去重副本不作为累计 Token 统计。原文引用可通过已鉴权的 `POST /local/desktop/history/read` 读取。

活动 KV 报告磁盘读写故障时，网关会以显存 KV 重启引擎。若客户端尚未收到流内容，网关按恢复后的容量重新装配提示并重试一次。已开始返回的流不会自动重放，下一轮使用恢复后的引擎。用户保存的 SSD 配置保留，下次手动启动时会再次生效。

目前可在 CPU 上验证原文保留、完整工具调用组、混合 KV 的因果注意力和故障标记。真实累计百万 Token、Windows 原生运行和 SSD 满盘后的 GPU 生成仍需实机验收。
