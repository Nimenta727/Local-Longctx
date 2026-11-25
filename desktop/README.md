# 远栈桌面

远栈直接加载本仓库的 Electron 工作区。主进程管理本地 FreeToken 和鉴权，渲染层通过受限的 IPC 发送请求。桌面的会话页、模型与缓存页及样式都在 `desktop/app`。

## 开发启动

安装 Node.js 24 和本地 Python 3.10+，然后在仓库根目录运行：

```bash
npm ci --prefix desktop
python desktop/launch_dev.py
```

在「模型与缓存」里选择一个可信 FreeToken 程序和本地 GGUF，启动模型。打包版使用自带运行时，只需要选择 GGUF。数据保存在 Electron 的用户目录中。设置 `LOCAL_LONGCTX_DATA_DIR` 可沿用旧版所在的本地数据目录。旧 Harness 格式会话文件继续留在原路径，新工作区的纯文本会话使用独立记录。

## 调整参数

启动时从引擎读取 KV、MoE、滑窗和 GDN 池中实际存在的项目。运行中拖动滑杆立即显示目标容量和组合显存估算。应用按钮只在预算允许、引擎空闲且配置版本匹配时可用。确认应用后，界面以引擎回读的容量为准。重置只清除未应用的草稿。

「启动参数」保存后在重启引擎时生效。实验性 SSD 总开关默认关闭。打开后可选择相应的子功能并调预算。活动 KV 使用内置引擎、Auto KV 精度和兼容的 Qwen3 MoE GGUF。

## 验收与打包

```bash
python desktop/verify_build.py
npx --prefix desktop playwright install chromium
npm --prefix desktop run test:browser
npm --prefix desktop run test:electron
```

浏览器用例使用标为模拟引擎的数据检查拖动和视觉布局。Electron 冒烟测试检查真实窗口和 IPC，NVIDIA 模型运行需要实机。 [Windows 打包](../docs/farstack.md#windows-构建)

旧版 Harness 源码预发行可以通过对应的 Git 标签重现。现行入口和安装包构建均使用本目录的 `package.json`。
