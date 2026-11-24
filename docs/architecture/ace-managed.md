# ACE managed-session preview

This is a separate opt-in workflow, not an invisible rewrite of OpenAI chat requests. The normal endpoint remains unchanged.

## Workflow

All requests are JSON POST, authenticated with the local gateway Bearer key, loopback only, and use the shared inference lock. Use /local/session/create with session, messages, allow_semantic (false by default). /local/session/read accepts session and optional revision. /local/session/append accepts session, expected_revision, expected_sha, messages (additional). /local/session/rollback accepts session, expected_revision, expected_sha, target_revision. Rollback creates a new revision, never deletes history.

POST /local/session/compact with session, expected_revision, expected_sha, telemetry_profile, estimates, segments and commit (false by default). Only explicitly unpinned assistant history older than the last four messages is eligible. User/system and recent turns remain untouched. Segment index refers to original message index. Provide anchors (literal strings to preserve), budget_chars, importance, access_frequency, dependency. Anchor matching is not a proof of preserved semantics. The extractive method includes an explicit archive marker and whole lines; full prior revisions are stored in SQLite with hashes. No external service or second model.

telemetry_profile: kv_used and kv_capacity are field paths (arrays of JSON object keys) from /v1/cache/status, with identical units; prefill_tps and active_requests are paths from /v1/stats. Inspect the exact installed FreeToken version first; no universal profile is asserted. Invalid paths, missing values, zero throughput or non-idle backend defer/reject. Current RAM and selected NVIDIA device are independently probed. No native pool rebuild or KV mutation.

estimates: growth_tokens_per_second, history_dependency, compact_seconds, expected_turns, prefix_recompute_tokens, cache_hit_fraction, seconds_since_compact, compact_peak_ram_gib, compact_peak_vram_gib. Explicit agent/operator estimates, not automatically measured. Candidate savings are marginal whole-prompt count estimates; actual combined prompt is counted and must reach target and fit output reserve with margin. FreeToken Anthropic count_tokens vs OpenAI template parity remains unverified.

The caller must explicitly set commit:true to change the managed revision. Preview is read-only except initialization of the database. CAS prevents stale revisions; commit checks backend idle again. Archive lives in state_dir/ace-sessions.sqlite3, not a GPU KV archive. Set private directory permissions/Windows ACLs; no encryption or automatic retention yet. Do not put secrets in prompts. Application must fetch revised messages and send them to normal completion API; OpenClaw does not yet consume managed sessions. No automatic background or live compaction. Exact history remains retrievable by revision, not necessarily in current model context. The caller should validate task quality before commit; literal preservation is not semantic equivalence. Future: timestamped telemetry and automatic segment scoring, native cache reclamation, session agent integration, bounded archive retention, GPU stress tests and upstream revision lock.

Sources: https://github.com/FlashML-org/FreeToken/blob/main/docs/cli.md ; https://github.com/FlashML-org/FreeToken/blob/main/docs/quickstart.md .
