<div align="center">

<img src="./docs/assets/mimiron-hero.svg" alt="Mimiron — the titan keeper of multi-agent pipelines" width="100%"/>

<br/>

[![tests](https://img.shields.io/badge/tests-197%20passing-22a86b?style=flat-square)](#testing)
[![python](https://img.shields.io/badge/python-3.11+-7a3ff5?style=flat-square)](https://www.python.org)
[![license](https://img.shields.io/badge/license-MIT-d6a542?style=flat-square)](./LICENSE)
[![status](https://img.shields.io/badge/status-v0.1.0%20·%20form%20complete-c490ff?style=flat-square)](./CHANGELOG.md)
[![claude code](https://img.shields.io/badge/claude%20code-plugin-ffd966?style=flat-square)](https://claude.com/claude-code)

**A multi-agent harness for Claude Code with quantitative gates, DAG-based parallel execution, and persistent loop — guarded by 14 safety pins.**

[Quick start](#quick-start) · [Concepts](#concepts) · [Architecture](#architecture) · [Documentation](#documentation) · [한국어](./README.ko.md)

</div>

---

## Why Mimiron

Most "AI coding agents" are a single LLM in a loop. That works for tiny edits and breaks the moment a feature needs *spec discipline*, *parallel work*, or *retry-without-drift*.

Mimiron is a **harness**, not an agent. It treats LLM output as a *suspect* and the file system as ground truth. Every phase transition is decided by a **deterministic gate**, every worker output is **hash-verified**, and every loop has a **safety pin** that stops the agent from spinning.

Named for the [titan keeper of Ulduar](https://wowpedia.fandom.com/wiki/Mimiron) — engineer-craftsman of mechanical guardians, obsessed with measured construction over speed.

## Quick start

In any Claude Code session:

```
/plugin marketplace add skarl86/mimiron
/plugin install mimiron@skarl86-mimiron
```

That's it for the plugin install — `/mimiron`, `/mimiron-status`, `/mimiron-resume`, `/mimiron-pause`, and `/mimiron-unstuck` slash commands are now live, along with the 8 skills, 3 worker agents, and 3 hooks (SessionStart / Stop / PostToolUse drift).

Then in your project, kick off a feature:

```
/mimiron "Add a /version endpoint to the Flask app"
```

The full 6-phase pipeline triggers: Socratic clarification → frozen spec → DAG of tasks → parallel worker dispatch → deterministic gate evaluation → finalize with a commit suggestion. `state.json` is the ledger your hooks (and you) can interrupt at any phase.

### Optional: deterministic CLI

The skills above call a small Python CLI (`mimiron`, `mimiron-bench`) for the deterministic lane. If you want to run those commands yourself (or your hooks need them on `$PATH`), install once:

```bash
git clone https://github.com/skarl86/mimiron /tmp/mimiron && cd /tmp/mimiron
uv pip install -e .         # or: pip install -e .
```

Then bootstrap a fresh project's mechanical toolchain in one shot:

```bash
mimiron init my-feature --bootstrap-toolchain=python-uv   # or python-pip | node-npm | go
```

This writes `.mimiron/_global/{mechanical.toml,thresholds.yaml}` from the `evals/` templates so `gate mechanical` works out of the box.

## The 6-phase pipeline

```
clarify ──τ──▶ spec ──q──▶ plan ──c──▶ execute ──a──▶ evaluate ──v──▶ finalize ─▶ done
   ▲             ▲           ▲            ▲│              ▲│
   │             │           │      retry │└── fail ──────┘│
   │             │           │       ≤3   │                │
   │             │           │            ▼                │
   └─────────────┴───────────┴─────── stuck ◀──── fail × 3 ┘
                                         │
                                         ▼
                                      paused (via unstuck)
```

Each arrow is a **gate** — a deterministic LLM-free check that decides phase transition:

| Gate | Phase exit | What it checks |
|---|---|---|
| **τ ambiguity** | clarify → spec | `ambiguity_score ≤ 0.20` (median-of-3, certainty band ±0.05) |
| **q quality** | spec → plan | `quality_score ≥ 0.85` (with reviewer-ratio penalty) |
| **c plan integrity** | plan → execute | DAG cycle-free + owned_files conflict-free + spec_hash frozen |
| **a artifacts** | execute → evaluate | All tasks committed, hashes match worker declarations |
| **v evaluate** | evaluate → finalize | Mechanical (build/test/lint) + Semantic (reviewer median-of-3) |

`fail × 3` → `stuck` → `unstuck` skill engages. The user decides; the agent does not auto-recover.

## Concepts

### 3-Lane separation

Every code path lives in exactly one lane. Cross-lane calls are *structurally* prevented.

```
Creative lane  →  skills (markdown) + agents (Task tool)
                  LLM-driven judgment, no direct state mutation.

Deterministic  →  CLI (mimiron, mimiron-bench)
                  Zero LLM calls. Pure file IO + Python.

Persistence    →  hooks (SessionStart, Stop, PostToolUse)
                  Light glue. Only re-entry + drift logging.
```

### 14-pin safety architecture

| Pin | Where | Why |
|---|---|---|
| **6-fold infinite loop defense** | spec § 5.4 | gate block → retry≤3 → consec_fail≥3 → unstuck → wall_clock 4h → token budget 500K |
| **4-fold judge defense** | spec § 6.4 | median-of-3 + temperature=0, certainty band, acceptance contract penalty, mutation opt-in |
| **5-fold outer-loop pin** | spec § 7.5.5 | benchmark suite halt: iteration_cap, asymptote, all_deferred, wall_clock, user_abort |

Total: 6 + 4 + 5 + spec_hash freeze (1) + 3-Lane structural (1) = **14 pins** + `unstuck` as personified safety mechanism.

### Spec freeze contract

Plan-time spec hash is recorded in `state.json`. Every subsequent CLI call (`scan`, `commit-task`, `gate semantic`, `archive`) re-hashes `spec.yaml` and **rejects** drift. The only way to unlock is `state.spec_unlocked=true` via `unstuck` flow.

### Self-host

Mimiron evaluates itself with `mimiron-bench`. The benchmark suite curates real merged PRs into reproducible fixtures (currently 3: B01–B03, drawn from production `naver-smartstore` traffic). Suite aggregate score gates `v0 → v1` graduation.

## Architecture

```
mimiron/
├── .claude-plugin/{plugin.json, marketplace.json}
├── commands/                  # /mimiron entry + 4 helpers
├── skills/                    # 8 creative-lane SKILL.md
│   ├── clarify/  spec/  plan/  execute/  evaluate/  finalize/
│   ├── unstuck/               # safety-pin personified
│   └── bench-judge/           # self-eval judge
├── agents/                    # 3 worker tiers (worker/tester/reviewer)
├── hooks/                     # 3 Python hooks + config
├── scripts/                   # mimiron + mimiron-bench bash entries
├── src/mimiron/               # deterministic Python (19 modules)
│   ├── cli.py                 # 9 subcommands
│   ├── state.py spec.py plan.py verdict.py artifacts.py
│   ├── scanner.py gates.py thresholds.py hash_util.py llm.py
│   └── bench/                 # self-eval CLI (run/list/compare/suite/judge)
├── benchmarks/                # B01, B02, B03 fixtures (real merged PRs)
├── evals/                     # 4 mechanical.toml templates
├── dogfood/                   # 3 archived runs (with defect reports)
└── tests/                     # 197 passing
```

## Documentation

| Document | What's inside |
|---|---|
| [`docs/superpowers/specs/2026-05-22-mimiron-design.md`](./docs/superpowers/specs/2026-05-22-mimiron-design.md) | 696-line design spec — architecture, 6-phase pipeline, gate rules, schemas |
| [`docs/HANDOVER.md`](./docs/HANDOVER.md) | Context bundle for post-compact Claude sessions |
| [`docs/ralph-loop-entry.md`](./docs/ralph-loop-entry.md) | How to drive Mimiron's own development with ralph-loop |
| [`dogfood/`](./dogfood/) | Self-eval run archives with defect reports |
| [`benchmarks/<id>/curation.md`](./benchmarks/) | Per-benchmark provenance + test strategy notes |

## Testing

```bash
.venv/bin/pytest -q        # 197 passing
.venv/bin/ruff check src/ tests/ hooks/
.venv/bin/mypy src/mimiron/
```

| Tier | What | Count |
|---|---|---|
| Unit | Pure Python, no LLM | 197 |
| Integration (`tests/integration/`) | CLI subprocess + tmp project sidecar | 8 |
| Self-eval (`mimiron-bench`) | Real merged PRs, reproducible fixtures | 3 |

## Status

**v0.1.0 — form complete.** Every spec § 4.1 component exists, every phase transition is automated, two dogfood runs (one defect-finding, one verification) closed the feedback loop with **zero remaining workarounds**.

| Area | State |
|---|---|
| Plugin layout (§ 4.1) | ✅ all components present |
| 6-phase auto flow | ✅ zero manual state edits |
| Safety pins (14 + unstuck) | ✅ specified, implemented, tested |
| 3-Lane separation | ✅ structurally enforced |
| Dogfood runs | ✅ 3 archived (8 defects found → 8 fixed) |
| Benchmarks | ⏳ 3 curated, real LLM judge interactive-only |
| `mimiron-bench suite ≥ 0.75` (real judge) | ⏳ pending interactive dogfood with real judge |

See [CHANGELOG.md](./CHANGELOG.md) for the road to v1.

## Contributing

Mimiron is *itself* the harness it builds. Use `/mimiron "<your contribution>"` and let it drive its own evolution. Defects discovered during a dogfood run are first-class artifacts — archive them in `dogfood/NNN-*.md` and fix in subsequent commits.

## License

MIT — see [LICENSE](./LICENSE).

---

<div align="center">

*Built measured, never fast. The keeper does not hurry.*

</div>
