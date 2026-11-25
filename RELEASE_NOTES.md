# Local-Longctx Studio v0.3.0-alpha.5

源码预发行 / Source prerelease · Python 3.10+ · Apache-2.0

## 本版更新 / What's new

- **实验性 SSD 总开关默认关闭。** 关闭时使用原有 RAM 和显存调节范围，启动时禁用 SSD 专家读取和 KV 检查点。开启后可分别启用两项功能，保存后重启生效。
- **专家权重按需读取。** 在兼容的 Qwen3 MoE GGUF 上，解码缓存未命中时按专家从模型文件读取。专家暂存上限可调 4–32 MiB，默认 4 MiB。
- **KV 前缀检查点。** 可将请求结束后的 BF16 KV 前缀写入本地数据目录，重启后匹配前缀时还原。单个文件上限可调 16–1024 MiB，默认 256 MiB。活动 KV 仍在显存。
- **桌面启动设置。** 可设置 MoE 策略、显存比例、RAM 和显存余量及主机权重估算。现有 Cache 面板继续提供空闲时的容量调节。

SSD is opt-in, with separate controls for on-demand expert reads and a persistent BF16 KV prefix checkpoint. The desktop exposes startup memory budgets alongside the existing idle cache sliders.

## 上机试用 / Getting started

1. 下载本版源码。运行 `python -m longctx --version` 应显示 `0.3.0a5`。桌面用户需要用新源码准备固定版本的 Harness 覆盖层。迁移时先退出旧服务，再将 `LOCAL_LONGCTX_DATA_DIR` 指向原数据目录或完整备份。 [桌面构建与数据迁移](https://github.com/Nimenta727/Local-Longctx/blob/v0.3.0-alpha.5/desktop/README.md)
2. 先保持 SSD 关闭，启动引擎并发送固定短提示，记录输出和首 Token 延迟。试用 SSD 时，按指南安装固定版本的 FreeToken 及本版补丁，选择兼容的单文件 Qwen3 MoE GGUF。在「启动参数」打开实验性 SSD 总开关，再选择子功能。旧配置也需要显式打开总开关。 [补丁安装与 GPU 验收](https://github.com/Nimenta727/Local-Longctx/blob/v0.3.0-alpha.5/docs/testing.md#freetoken-专家换入实验)
3. 试用 KV 恢复时，把本地数据目录放在 SSD 上。完成请求后重启，再发送相同提示，比较输出、缓存命中 token 数和首 Token 延迟。 [文件位置、清理与验证](https://github.com/Nimenta727/Local-Longctx/blob/v0.3.0-alpha.5/docs/testing.md#ssd-kv-前缀检查点实验)

## 验证范围 / Verification

44 项 Python 测试、桌面 SSD 设置回归和定向 TypeScript 检查通过。已验证 FreeToken 补丁可应用到固定修订版，CPU 侧验证了专家张量读取和 KV 页恢复。完整 Electron 会话、NVIDIA 实机生成、低 RAM 稳定性和 SSD 性能仍待验证。本版提供源码归档和 FreeToken 补丁。

更广的 Harness 回归共 245 项，231 项通过，工具输出回归的 14 项在本环境出现 Node 子进程文件描述符错误及超时。

The source prerelease includes the FreeToken patch. CPU checks cover expert tensor reads and KV restoration. The broader Harness run passed 231 of 245 tests. The 14 tool-output failures involved Node child-process file descriptors and timeouts. Full Electron and NVIDIA runtime validation are pending.
