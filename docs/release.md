# 发行 / Release

Version / 版本: **v0.3.0-alpha.1** (Python 0.3.0a1), source preview only / 仅源码预发行。

The main branch and release preparation branch contain the source; a branch is not a tag or published release. 主分支及预发行准备分支是源码，不等于 Git tag 或 GitHub Release。当前没有已验证安装包 / No verified binary.

After cloning the exact release candidate, run `python scripts/check_release.py` in a clean checkout. Once tests pass and you have authorized GitHub CLI credentials, run:

```bash
gh release create v0.3.0-alpha.1 --target "$(git rev-parse HEAD)" --prerelease --title "Local-Longctx Studio v0.3.0-alpha.1" --notes-file RELEASE_NOTES.md
```

上面是 Bash 示例，先确认 HEAD 对应预发行准备分支的提交；不要从其他分支发布。This is a Bash example; verify HEAD is the intended candidate before publishing. GitHub generates source ZIP/tar.gz; no Windows installer should be attached until tested. GitHub 自动生成源码归档；未通过实机验收前不上传安装包。

Never publish upstream under its original product identity or distribute unreviewed binaries. 保留上游许可证及归属，正式发行前完成独立品牌、签名、依赖锁、SBOM 和更新通道审核。
