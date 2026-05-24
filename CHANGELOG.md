# Changelog

All notable changes to Mimiron. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) · semver: [`MAJOR.MINOR.PATCH`](https://semver.org/spec/v2.0.0.html).

## [v0.1.0] — 2026-05-23 — **Form complete**

The full spec § 4.1 layout exists, every phase transition is automated, two dogfood runs (defect-finding + verification) closed the feedback loop with zero remaining workarounds.

### Phase A — Deterministic core (Mar 2026)

- 9-subcommand CLI: `init`, `ls`, `status`, `scan`, `gate`, `commit-task`, `archive`, `pause`, `resume`
- 5-schema data model (state, spec, plan, verdict, artifacts) with strict validation + forward-compat unknown-key filtering
- DAG scanner (cycle + ownership + dangling-depends detection), mechanical gate runner, schema-version policy
- 4-bench self-evaluation CLI: `list`, `run`, `compare`, `suite` — with `--similarity-from` file-backed judge contract
- 2 curated benchmarks at A-graduation (B01 welcome-message-fix)
- 73 unit tests + 8 integration tests at A-graduation

### Phase B — Multi-agent harness (May 2026)

- **8 skills** wrapping the creative lane:
  - `clarify`, `spec`, `plan`, `execute`, `evaluate`, `finalize` (the 6-phase pipeline)
  - `unstuck` — the safety pin personified
  - `bench-judge` — self-eval LLM judge producer
- **3 agents** for worker tiers: `mimiron-worker` (default), `mimiron-tester` (test-only scope), `mimiron-reviewer` (judgment-only, no Write/Edit tools)
- **3 hooks + config**: `session-start` (in-progress slug context), `stop-hook` (persistent loop re-entry + wall_clock/token cap), `post-toolwrite` (drift detection → `drift.log`)
- **5 commands** as user entry points: `/mimiron`, `/mimiron-resume`, `/mimiron-status`, `/mimiron-pause`, `/mimiron-unstuck`
- **2 new CLI commands**: `mimiron archive` (phase=finalize → done + persistent=false), `mimiron init --bootstrap-toolchain` (4 toolchain templates)
- **2 new gates**: `plan_integrity` (DAG validation + spec_hash check → phase=execute), `artifacts` (scan phase_done → phase=evaluate)
- **3 curated benchmarks** (B01–B03, sourced from real merged PRs in `naver-smartstore`): bug fix (subtractive), bug fix (additive guards), pure refactor — difficulty spread
- **4 mechanical fixtures** in `evals/`: `python-uv`, `python-pip`, `node-npm`, `go`
- 197 passing unit tests, ruff + mypy clean

### Dogfood — Self-host signal

| Run | Subject | Outcome |
|---|---|---|
| 001 | B01 manual end-to-end (A-graduation) | passed |
| 002 | `bench-list-json` (Add `--json` to `bench list`) | 8 defects found (3 critical, 5 minor) |
| 003 | `status-json-flag` (Add `--json` to `status`) | **Zero defects, zero workarounds** — fix verification |

All 8 defects from run 002 were fixed before run 003. Run 003 traversed the full 6-phase pipeline with no manual state-edit interventions.

### Safety architecture

14 pins specified, implemented, and tested:

- **6-fold infinite loop defense** (gate blocking, task retry ≤ 3, consecutive gate fail ≥ 3, unstuck flow, wall_clock 4h, token budget 500K)
- **4-fold judge defense** (median-of-3 + temperature=0, certainty band ±0.05, acceptance contract reviewer-ratio penalty, mutation rule opt-in)
- **5-fold outer-loop safety pin** (iteration_cap, asymptote, all_deferred, wall_clock 24h, user_abort)
- spec_hash freeze (1) + 3-Lane structural separation (1)

Plus `unstuck` as the personified safety mechanism — human-in-the-loop recovery only, no auto-resolution.

### Notable defects fixed in v0.1.0 (from dogfood 002)

- `.mimiron/_global/` bootstrap mechanism added (was absent — first-run friction)
- `gate plan_integrity` and `gate artifacts` close the phase-transition gap (was: manual `state.json` edit required)
- `Thresholds.load_or_default` forward-compat for unknown keys
- `sha256_file` accepts `str | Path`
- `spec/SKILL.md` adds verify-kind field table + hypothesis schema
- `agents/mimiron-worker.md` corrects `python3` to `.venv/bin/python` for module-import recipe

## [Unreleased] — toward v0.3.0

- `benchmarks/_CURATION_GUIDE.md` — 5-rule guide for `issue.md` root-cause hint level + B01 retroactive signal boost (#25)
- bench-judge: J5 (apply-check) dimension — `git apply --check` against base_ref as deterministic 5th rubric, optional `apply_check` JSON field, backward-compat fallback to 4-dim mean (#21)
- bench-judge: 4-label certainty band (`trivial-certain` / `discriminating-certain` / `failure-certain` / `uncertain`) replacing the old binary certain/uncertain. Optional `certainty_label` JSON field. Full coverage via 0.35 / 0.85 thresholds (#23)
- bench-judge: deterministic prompt-variation across median-of-3 rounds (`v030-r1-canonical` / `v030-r2-shuffle-actual-first` / `v030-r3-regression-strict`). Optional `variation_seeds` JSON metadata. Empirical result on dogfood/005 candidates: null aggregate-spread effect, but r3 strict-emphasis produces directional pull on regression-risky candidates (B01, B02) — hypothesis partially rejected per spec (#22)

## [v0.2.0] — 2026-05-24 — **Bench foundation**

- B04 + B05 benchmark curation (diversify suite signal: hard fix, feat)
- Interactive dogfood with real LLM judge (run `mimiron-bench-judge <id>` skill on real session)
- Plan_integrity / artifacts gate `needs_review` band handling (currently only pass/fail)
- Drift hook upgrade: v0 warn → v1 reject (PostToolUse decision=block)
- Plugin self-contained `/mimiron` entry (no external skill dependency)
- User-language threading + gate(artifacts) `needs_review` band
- Hooks routed through `CLAUDE_PLUGIN_ROOT` + `CLAUDE_PROJECT_DIR`

## [Unreleased] — toward v1.0.0 (function complete)

- `mimiron-bench suite_aggregate ≥ 0.75` with real LLM judge across ≥ 3 benchmarks (cutoff_global)
- ≥ 3 benchmarks `passed` (deferred → real verdict)
- ≥ 5 dogfood runs archived
- Live user-feature dogfood (a real feature shipped through `/mimiron` end-to-end)
- Deferred decisions confirmed with dogfood evidence (spec § 8: 7 items)

[v0.1.0]: https://github.com/<you>/mimiron/releases/tag/v0.1.0
[Unreleased]: https://github.com/<you>/mimiron/compare/v0.1.0...HEAD
