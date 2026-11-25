# FreeToken in FarStack

FreeToken source is derived from FlashML-org/FreeToken at
94938a6a576926d384986fbe8cd7f1a4eb6d687e. Its source remains under Apache-2.0.
The original README, license, file notices and vendored ggml license remain in this directory.

FarStack adds SSD expert loading, KV prefix checkpoints and opt-in active KV tiering, and adapts the Windows
build for CUDA library locations, MSVC options and the Windows Triton package.
This Windows fork targets GPU expert execution. It does not build the CPU MoE
extension on Windows. Windows CUDA runtime verification is pending.
