# Local-Longctx Studio — source integration preview

This is a pinned, reproducible **source overlay** for DeepSeek Harness, not a new frontend or a bundled installer. The upstream tool packages are left intact. Its MIT license and copyright remain in the checked-out source. No claim of upstream endorsement.

Developer preparation:
1. Review the locked source and upstream dependency/build instructions in its README.
2. From this repository run `python desktop/prepare_harness.py`.
3. Install the locked upstream dependencies using its documented Node/pnpm toolchain in desktop/upstream. Build native dependencies according to upstream instructions. Do not use upstream release/publish targets.
4. Run `python desktop/launch_dev.py` from the root.

The new model settings panel selects trusted FreeToken and local GGUF paths via native file dialogs; selects context, model limit, output, threads, memory ratio and KV format; starts/stops a parent-owned Local-Longctx worker. Model-provider creation includes a local preset that fills the exact current native context and an ephemeral local connection key. Existing upstream credential storage and save confirmation remain unchanged. After restarting the engine, update the existing provider's key through its original edit UI; automatic credential rotation and provider selection are not implemented. No renderer shell access was added.

Only development mode is supported. Engine configuration is generated in the app data directory; no manual JSON edits are necessary for these preview controls. Existing API authentication remains, renderer access is origin/main-window scoped. A native confirmation is required before spawning the chosen executable. Native model capability remains a declared/experimental setting, not verified 1M.

## Important limitations
No frontend TypeScript compile, actual Electron start, real GPU or end-to-end tool call test in this environment. Existing backend rejects tool calls and image input; retaining upstream plugins does not make them usable by the current local model. ACE managed APIs exist but Harness's native compaction is not yet connected to them. No independent installer. Original product-facing package name and vector marks are patched in the overlay; raster icons, installer resources, login/onboarding copy, update/publisher identity, deep links, telemetry and account flows still need review. Do not release or imply full rebranding yet. Development launch does not certify network isolation. Retain upstream notices and security gates. Use no real credentials until audit is complete.
