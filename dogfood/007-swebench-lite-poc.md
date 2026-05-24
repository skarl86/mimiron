# Dogfood Case 007 — SWE-bench Lite Adapter PoC

- **Date**: 2026-05-24
- **Scope**: PR #26 — SWE-bench Lite dataset adapter PoC (importer, --clarification-from flag, --swebench-tests flag, orchestration skill)
- **Status**: PR merged (`6a4ceb9`). 351 tests passing. Real-data dogfood found and fixed 1 bug; identified 3 known limits as v0.4.0 milestone seeds.
- **Method**: brainstorming → spec (`docs/superpowers/specs/2026-05-24-swebench-lite-adapter-design.md`) → plan (`...plans/...`) → subagent-driven execution (11 tasks × implementer + spec-reviewer + code-reviewer cycle) → real-data dogfood on 10 SWE-bench Lite instances.

---

## §A — Implementation (PR #26, 13 commits)

### What shipped

- **Dataset importer** (`src/mimiron/bench/swebench_import.py`, 220 LOC) — HF / JSONL → `benchmarks/SWE-LITE-<id>/` fixtures with deterministic stratification (`patch_bytes + 2*FAIL_TO_PASS + 3*touched_files` quantile, `max_per_repo=4`).
- **`mimiron init --clarification-from <file>`** flag — direct injection of external clarification.md, jumps `state.phase` from `clarify` to `spec`. *General-purpose* feature, not SWE-bench-specific.
- **`mimiron-bench run --swebench-tests`** flag — hybrid verdict on candidate-applied worktree: pytest selector runner (`src/mimiron/bench/swebench_runner.py`), `compute_bench_score(test_pass_rate, similarity, 0.6, 0.4)` per spec §7.
- **`mimiron-swebench` skill + `/mimiron-swebench`** — sequential suite orchestrator (`skills/mimiron-swebench/SKILL.md`).
- **`[swebench]` optional extra** (`pyproject.toml`) — `datasets>=2.14`. Core 의존성 영향 없음.

### Subagent-driven execution observations

- **Review cycle ROI**: 11 tasks × spec-review + code-review found 5 real issues (T2 sphinx-doc regression test, T4 unhandled FileNotFoundError, T6 regex over-count, T7 candidate-apply 누락 + bench_score formula drift). *Plan 그대로 copy 된 코드도 spec 과 drift 했음* — review cycle 이 catch.
- **False alarm rate**: 1/8 reviewer findings (T2's `repo_dir_name` "bug" — verified false by direct Python repl). Importance of verifying before acting on review feedback.
- **Implementer caught reviewer error**: T6 cleanup — implementer rejected my prescription (`findall()[-1]`) because regression test required a stronger fix (summary-line-anchored regex). Honest disagreement preserved correctness.

### Closed via

PR #26 (commit `6a4ceb9` merge to main). All 11 tasks T1-T11 + docs commit + JSON-string fix landed together.

---

## §B — Real-data dogfood: HF JSON-string deserialization bug

### Discovery

10 SWE-bench Lite instances imported via `mimiron-bench swebench import --from-hf --stratified 10 --seed 42`. First `mimiron-bench run SWE-LITE-mwaskom__seaborn-3190 --swebench-tests` returned:
```
"reason": "env_error"
"stderr_tail": "ERROR: path cannot contain [] parametrization: [\n\n"
"selectors_total": 5894
```

Inspecting `_swebench.json`:
```python
>>> m['FAIL_TO_PASS'][:3]
['[', '"', 'l']
```

**Root cause**: HuggingFace stores `FAIL_TO_PASS` / `PASS_TO_PASS` as JSON-encoded **strings** (e.g. `'["test_a", "test_b"]'`), not Python lists. `write_fixture` then called `list(instance["FAIL_TO_PASS"])` which iterates the string into chars.

### What unit tests missed

- `tests/fixtures/swebench_sample.jsonl` already had `FAIL_TO_PASS` as a *Python list literal* (created from the plan, not from HF data). Unit tests + integration smoke all passed.
- The bug only surfaces against *real HF data shape*. This is a textbook case for why fixture-only testing is insufficient.

### Fix (commit `4b185a3`)

`_normalize_json_list_fields()` helper applied at both loader entry points:

```python
_JSON_LIST_FIELDS = ("FAIL_TO_PASS", "PASS_TO_PASS")

def _normalize_json_list_fields(rec):
    for key in _JSON_LIST_FIELDS:
        v = rec.get(key)
        if isinstance(v, str):
            rec[key] = _json.loads(v)
    return rec
```

2 regression tests added (JSON-string round-trip + list-already pass-through).

### Bonus finding

Pre-fix, the `stratify_instances` algorithm was computing `len(FAIL_TO_PASS)` on strings → **character count** instead of *test count*. Difficulty quantile was based on string length, not actual test count. Post-fix, the 10-instance stratified sample changed entirely (seed=42 same, but features different). The earlier dogfood was effectively running on garbage features.

### Verification

- 351 tests (was 349, +2 regression)
- Re-import produced clean fixture (FAIL_TO_PASS: list, max 124,044 selectors observed for xarray-4493 — exposing a *different* known limit, see §D).

---

## §C — `mimiron-bench run --swebench-tests` adapter validation

10 fixtures + 7 repos cloned (`.bench-clones/swebench/`, ~1.6GB). Candidate diff = `expected.diff` (gold) staged at `.mimiron/_bench/_input/<id>.diff` for each.

### Wiring verification

| Component | Expected | Observed |
|---|---|---|
| `_find_candidate_diff` lookup | hits `_input/<id>.diff` | ✓ `candidate_found: true` |
| `git apply --whitespace=nowarn` | applies cleanly inside `isolate_at_ref` worktree | ✓ `apply_status: applied` |
| `_swebench.json` selector load | post-fix → list | ✓ `selectors_total` matches actual `len(FAIL_TO_PASS) + len(PASS_TO_PASS)` |
| Hybrid verdict shape | `resolved`, `bench_score`, `test_pass_rate`, `details.swebench` | ✓ all fields present |

### What blocked actual evaluation

All 10 instances returned `env_error` from the pytest invocation (see §D for taxonomy). Adapter *wiring* validated; actual *test execution* requires Docker harness work (out of PoC scope, spec §11 Risk #5 anticipated).

---

## §D — Mimiron pipeline pilot on django-11964 (spec phase)

### Setup

```bash
cd /tmp/swebench-dogfood
uv ... mimiron init swebench-django-11964 --clarification-from benchmarks/SWE-LITE-django__django-11964/issue.md --no-persist
```

Result: `state.phase = "spec"`, `clarification.md` (44 lines) staged. Adapter validated for *general* external-issue ingestion.

### Spec decantation

44-line SWE-bench `problem_statement` (TextChoices/IntegerChoices field returning enum member instead of value) decanted into `spec.yaml`:
- 1 goal sentence
- 3 constraints (backward-compat, scope-limit, public-API-invariance)
- 4 acceptance_criteria (3 `kind: test`, 1 `kind: grep`)
- 5 ontology terms
- 2 hypotheses (with confidence)
- self-evaluated `quality_score: 0.82`

### Gate verdict

```json
{"verdict": "needs_review", "score": 0.82,
 "path": ".mimiron/swebench-django-11964/evaluation/quality.json"}
```

Threshold `spec_quality_min=0.85`, certainty band `[0.80, 0.90]` → `needs_review`. **This is the design working exactly as intended** — spec quality just below threshold, in the band, gate flagged for human judgment instead of auto-passing or hard-rejecting.

### Self-identified spec weaknesses

- AC01 and AC02 share an identical `verify.command` (no unique signal — both run `model_enums` tests). The reason `quality_score` is 0.82 not higher.
- AC04's `grep` pattern `self\.value` is fragile (assumes a specific implementation idiom).
- H02 confidence 0.65 — appropriate hedging on implementation hypothesis.

### Plan / execute / evaluate phases

Not attempted in this dogfood session. Pipeline can resume from a *fresh Claude Code session* via `/mimiron-resume swebench-django-11964` at `/tmp/swebench-dogfood`. State preserved on disk (`.mimiron/swebench-django-11964/`).

---

## §E — v0.4.0 milestone seeds

Three PoC-revealed limits, each a candidate GitHub issue + spec for a follow-up PR:

### Limit 1: CWD dependency

- **Symptom**: `mimiron init`, `mimiron gate`, `mimiron-bench run` all resolve `.mimiron/<slug>/` relative to `Path.cwd()`. Multi-project operation (e.g. running mimiron *on* `/tmp/swebench-dogfood/` from a Claude Code session rooted at `/home/namgee/Development/private/mimiron/`) fragile.
- **Manifestation in this dogfood**: had to use `cd /tmp/swebench-dogfood && uv --project /home/namgee/... run mimiron ...` everywhere; could not invoke `mimiron:spec` skill directly because skill's CWD was the dev workspace, not the slug location.
- **Fix surface**: global `--project <path>` flag or `MIMIRON_PROJECT` env var, with all `Path.cwd()` calls routed through a single helper.
- **Estimated**: 2-4 hours brainstorm → spec → execute. Touches every `Path.cwd()` site in `cli.py` and `bench/cli.py`.

### Limit 2: Subprocess args limit

- **Symptom**: `swebench_runner` passes all selectors as `pytest` args. xarray-4493 has 124,044 selectors → ARG_MAX hit. Even smaller instances (matplotlib 770, django 1242) approach the limit.
- **Workaround**: pytest with module-path collection + parse-by-selector from stdout. SWE-bench's official approach.
- **Fix surface**: rewrite `run_swebench_tests` to (a) group selectors by module, (b) run pytest at module granularity, (c) match per-test results from output.
- **Estimated**: 4-6 hours. Affects only `swebench_runner.py` + tests.

### Limit 3: Worktree environment bootstrap

- **Symptom**: `isolate_at_ref` does `git checkout` but no `pip install -e .`. Most candidates fail with `ImportError: cannot import name X from Y`. sympy uses `bin/test`, django uses `tests/runtests.py`, matplotlib uses `pytest` — per-instance variation.
- **Anticipated by**: spec §11 Risk #5 ("Docker 없이 의존성 충돌").
- **Honest assessment**: this is **why SWE-bench's official evaluator uses Docker**. Each instance has an `environment_setup_commit` and a per-repo Dockerfile. Reimplementing this without Docker is a major undertaking.
- **Fix surface options**: (a) integrate with SWE-bench's official harness — call out via `swebench-runner` PyPI package; (b) write our own Docker bootstrap per instance; (c) defer to v1.0+ as scope expansion. Recommendation: option (a) — wrap, not reinvent.
- **Estimated**: option (a) ~1-2 days, option (b) 1-2 weeks.

### Filing

To be filed as GitHub issues with `milestone: v0.4.0` label. Limits 1 and 2 are mimiron-internal improvements; Limit 3 is an architecture decision warranting brainstorm.

---

## Observations

- **`--clarification-from` re-use potential**: not just SWE-bench. Any external trigger (Slack incident, Linear ticket, ralph-loop `wrap.md`, post-mortem replay) that can produce a markdown file can now bypass clarify. This is a *general* upgrade hiding inside a *specific* PoC.
- **Spec discipline survives external context**: mimiron's `quality_score` + certainty band machinery generated an *honest* `needs_review` verdict on a real SWE-bench issue. The pipeline didn't pretend the spec was perfect; it flagged the band gap.
- **PoC dogfood >> unit-test dogfood**: 351 tests passed before this dogfood ran. 2 of those tests were JSON-string regressions added *because of* this dogfood. The bug was structurally invisible to fixture-shaped tests.
- **`bench_score` formula drift in T7** — caught by review, not by tests. Tests were passing; spec §7 formula was simplified out during plan-to-code translation. This is exactly the kind of drift the spec/code-reviewer two-stage cycle is built to catch.

---

## Cross-references

- PR #26 — https://github.com/skarl86/mimiron/pull/26 (merged)
- Spec — `docs/superpowers/specs/2026-05-24-swebench-lite-adapter-design.md`
- Plan — `docs/superpowers/plans/2026-05-24-swebench-lite-adapter.md`
- Pilot state — `/tmp/swebench-dogfood/.mimiron/swebench-django-11964/` (local, not committed)
- v0.4.0 issues — to be filed
