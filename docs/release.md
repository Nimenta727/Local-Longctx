# 源码预发行 / Source release

当前版本 / Current version **v0.3.0-alpha.4** · Python `0.3.0a4`

从已发布版本下载 GitHub 生成的 ZIP 或 tar.gz。桌面用户按固定 Harness 指南准备源码和依赖。 / Download the GitHub source archive and follow the pinned desktop setup if needed. [GitHub Release](https://github.com/Nimenta727/Local-Longctx/releases/tag/v0.3.0-alpha.4) · [桌面指南 / Desktop guide](../desktop/README.md)

## 维护者发行步骤 / Maintainer workflow

1. 同步 README、变更日志、发行说明、`pyproject.toml` 和 `longctx/__init__.py` 里的版本信息。
2. 在候选提交上运行 `python scripts/check_release.py`，按验证文档记录已完成的测试和待验证项。
3. 推送候选提交，再用其完整 SHA 创建 GitHub 预发行版，确认标签指向该提交并检查发行说明。

```bash
gh release create v0.3.0-alpha.4 --target "$(git rev-parse HEAD)" \
  --prerelease --title "Local-Longctx Studio v0.3.0-alpha.4" \
  --notes-file RELEASE_NOTES.md
```

当前发行提供项目源码。桌面安装包需另行完成实机验收、品牌与第三方依赖审计、SBOM 和签名。 / Desktop installers require separate runtime validation, brand and dependency review, an SBOM, and signing. [验证 / Verification](testing.md) · [第三方许可 / Third-party notices](../THIRD_PARTY.md)
