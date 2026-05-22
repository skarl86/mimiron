# Dogfood Case 001 — B01 Manual Run

- **Date**: 2026-05-22
- **Benchmark**: B01-welcome-message-fix (ts-cxdm/workspace#1299)
- **Result**: deferred (expected for v0 manual mode)
- **test_pass_rate**: 1.0
- **Infra verified**:
  - git worktree isolation ✓
  - test_command run inside worktree ✓
  - parse_generic/pytest output ✓
  - status saved to `.mimiron/_outer/status/` ✓
  - bench CLI `list` + `run` works ✓
- **Base vs target sanity**: test_command exit=1 at base, exit=0 at target ✓
- **Next**: similarity_provider integration (Phase B), then re-run for `passed` verdict
