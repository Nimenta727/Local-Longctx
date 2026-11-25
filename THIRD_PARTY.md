# 第三方组件 / Third-party components

| Component / 组件 | License and scope / 许可与范围 |
| --- | --- |
| [FreeToken](https://github.com/FlashML-org/FreeToken) | Apache-2.0, source vendored at `94938a6a576926d384986fbe8cd7f1a4eb6d687e` with FarStack's Windows and storage changes / 内置源码及远栈的 Windows、存储修改 |
| [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) | MIT, retained in the legacy desktop overlay / 旧版桌面覆盖层保留其 MIT 声明 |
| [Electron](https://www.electronjs.org/) | MIT, desktop shell / 桌面运行时 |
| Python | PSF; standard library / 标准库 |
| Models / 模型 | User-provided, separately licensed / 用户提供，各自授权 |

远栈是独立项目。FreeToken、ggml 及 DeepSeek Harness 的上游署名保留在相应的源码与许可文件中。 [FreeToken 修改声明](vendor/freetoken/FARSTACK.md)

发布前逐项检查确切修订版本、依赖、模型及素材许可证，生成 SBOM，审查商标、更新通道及凭证处理。源码预览未捆绑第三方二进制、模型或上游品牌素材。Before distributing binaries, verify exact revisions, dependencies, model and asset licenses, generate an SBOM, and review trademarks, update channels and credentials. This source preview bundles no upstream executables, weights or upstream brand assets. LICENSE 保持原始法律文本 / The LICENSE file remains the original legal text.
