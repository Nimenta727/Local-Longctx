# Verification gates

Status: test code added; execution in a real checkout and model/hardware testing not yet verified.

## Unit / protocol
Run python -m unittest discover -s tests -v. Current tests cover command construction, config validation, capacity math, request admission, isolated provider config. Next add fake HTTP backend integration, SSE interruption, auth failures, malformed input, concurrency and lifecycle failure injection; then actual upstream server tests.

## Integration
Record exact Python, llama.cpp build and OpenClaw revision. Run small model CPU-only; verify startup actual reported context, model alias, JSON and SSE, wrong auth denied, over-budget rejected, no cloud fallback, no tool execution, clean process shutdown. Compare token preflight vs actual usage for system prompts and templates. Confirm all upstream OpenClaw tools disabled and no network channels configured. Do not treat the provider integration as a security sandbox. OpenClaw logs and model logs may contain sensitive data; keep local and do not publish unredacted.

## Long context
Test total context 32K / 128K / 256K / 512K / 1M with output reserved. Record actual prompt tokens, requested limit, model and binary SHA256, hardware, driver, KV type, layer placement, batches, cold/warm runs. Test multiple retrieval positions and distractors, cross-file and multi-hop reasoning. Repeat at least 3 runs. Capture TTFT, output TPS, peak process RSS and GPU memory using platform profilers. No silent truncation or semantic downgrade. Reject configurations that cannot finish or exceed memory budget.

## Release
No minimum hardware claim until measured. No full offline/packaged desktop claim until all dependencies pinned, SBOM/license review, OS-level permission and network tests, installer/uninstaller and recovery pass. Do not publish models or upstream binaries without license review.
