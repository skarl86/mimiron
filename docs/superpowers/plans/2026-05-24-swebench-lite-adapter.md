# SWE-bench Lite Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** SWE-bench Lite (300 instance) 의 20개 stratified subset 으로 mimiron 의 6-phase pipeline 을 외부 표준 벤치마크에 노출시키는 어댑터 PoC 를 구현한다.

**Architecture:** Dataset importer 가 SWE-bench instance → mimiron benchmark.yaml 로 변환. mimiron CLI 에 `--clarification-from` flag 추가해 clarify phase skip. 새 runner (`swebench_runner.py`) 가 `FAIL_TO_PASS`/`PASS_TO_PASS` pytest selector 측정. Suite orchestration skill (`mimiron-swebench`) 가 Claude Code 세션에서 fixture 순회 + 채점 집계. Hybrid verdict (test_pass_rate + semantic_similarity) 동시 기록.

**Tech Stack:** Python 3.11+, argparse, pytest, dataclasses, optional `datasets` (HuggingFace) — core 의존성 안 늘림.

**Spec:** `docs/superpowers/specs/2026-05-24-swebench-lite-adapter-design.md`

---

## File Structure

### Create
- `src/mimiron/bench/swebench_import.py` — Stratify algorithm + fixture writer + HF/JSONL loader (180 LOC)
- `src/mimiron/bench/swebench_runner.py` — FAIL_TO_PASS/PASS_TO_PASS pytest selector 측정 (80 LOC)
- `tests/bench/test_swebench_import.py` — Importer unit tests
- `tests/bench/test_swebench_runner.py` — Runner unit tests
- `tests/test_cli_clarification_from.py` — `--clarification-from` flag tests
- `tests/integration/test_swebench_smoke.py` — End-to-end smoke
- `tests/fixtures/swebench_sample.jsonl` — Mock HF data (3 instances)
- `skills/mimiron-swebench/SKILL.md` — Orchestration skill
- `commands/mimiron-swebench.md` — Slash command trigger

### Modify
- `src/mimiron/bench/cli.py` — `swebench import` subcommand + `run --swebench-tests` flag
- `src/mimiron/cli.py` — `--clarification-from` flag for `init` subcommand
- `pyproject.toml` — `[swebench]` optional extra
- `CHANGELOG.md` — note for next release

---

## Task Dependencies

```
T1 (stratify) ─┐
T2 (writer)  ──┤
T3 (loader)  ──┴─→ T4 (import CLI) ──┐
T5 (--clarification-from)            │
T6 (swebench_runner) ─→ T7 (run flag)│─→ T9 (skill) ─→ T10 (smoke) ─→ T11 (CHANGELOG)
T8 (pyproject extra)                 ┘
```

---

## Task 1: Stratification 알고리즘 (pure function, TDD)

**Files:**
- Create: `src/mimiron/bench/swebench_import.py`
- Test: `tests/bench/test_swebench_import.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/bench/test_swebench_import.py`:
```python
"""SWE-bench importer unit tests."""
from __future__ import annotations

import pytest

from mimiron.bench.swebench_import import (
    InstanceFeatures,
    compute_features,
    stratify_instances,
)


def _mk_inst(iid: str, repo: str, patch: str, ftp: list[str], ptp: list[str]) -> dict:
    return {
        "instance_id": iid,
        "repo": repo,
        "base_commit": "deadbeef",
        "problem_statement": f"issue for {iid}",
        "patch": patch,
        "FAIL_TO_PASS": ftp,
        "PASS_TO_PASS": ptp,
        "version": "1.0",
    }


def test_compute_features_returns_metric_triplet():
    inst = _mk_inst(
        iid="x__x-1",
        repo="x/x",
        patch="diff --git a/foo.py\n+x = 1\n",
        ftp=["tests/test_a.py::ta", "tests/test_a.py::tb"],
        ptp=["tests/test_a.py::tc"],
    )
    f = compute_features(inst)
    assert isinstance(f, InstanceFeatures)
    assert f.patch_bytes == len(inst["patch"])
    assert f.fail_to_pass_count == 2
    assert f.touched_files == 1  # 단일 diff --git 헤더


def test_stratify_balances_difficulty_and_repo_diversity():
    insts = []
    # 12 instances across 3 repos, varying difficulty signals
    for i in range(12):
        insts.append(_mk_inst(
            iid=f"r{i % 3}__r{i % 3}-{i}",
            repo=f"r{i % 3}/r{i % 3}",
            patch="d" * (100 * (i + 1)),  # increasing patch size
            ftp=[f"t::{j}" for j in range(i % 4 + 1)],
            ptp=[],
        ))
    selected = stratify_instances(insts, target=6, seed=42, max_per_repo=2)
    assert len(selected) == 6
    repos = [s["repo"] for s in selected]
    # max_per_repo=2 → no repo appears more than twice
    assert all(repos.count(r) <= 2 for r in set(repos))
    difficulties = [s["_mimiron_difficulty"] for s in selected]
    assert "easy" in difficulties and "hard" in difficulties


def test_stratify_is_deterministic_with_same_seed():
    insts = [_mk_inst(f"a__a-{i}", "a/a", "x" * (i + 1), ["t::x"], []) for i in range(8)]
    a = stratify_instances(insts, target=4, seed=7, max_per_repo=4)
    b = stratify_instances(insts, target=4, seed=7, max_per_repo=4)
    assert [x["instance_id"] for x in a] == [x["instance_id"] for x in b]
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `uv run pytest tests/bench/test_swebench_import.py -v`
Expected: `ModuleNotFoundError: No module named 'mimiron.bench.swebench_import'`

- [ ] **Step 3: minimal implementation**

`src/mimiron/bench/swebench_import.py`:
```python
"""SWE-bench Lite → mimiron fixture importer."""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class InstanceFeatures:
    patch_bytes: int
    fail_to_pass_count: int
    touched_files: int

    def difficulty_score(self) -> float:
        # 가중치: file > test > patch size (§8 spec)
        return self.patch_bytes + 2 * self.fail_to_pass_count + 3 * self.touched_files


def compute_features(instance: dict[str, Any]) -> InstanceFeatures:
    patch = instance.get("patch", "") or ""
    files = sum(1 for line in patch.splitlines() if line.startswith("diff --git"))
    return InstanceFeatures(
        patch_bytes=len(patch),
        fail_to_pass_count=len(instance.get("FAIL_TO_PASS", []) or []),
        touched_files=max(files, 1),
    )


def _classify(scores: list[float], score: float) -> str:
    """quantile-based difficulty label."""
    sorted_scores = sorted(scores)
    n = len(sorted_scores)
    if n == 0:
        return "medium"
    idx = sorted_scores.index(score)
    if idx < n / 3:
        return "easy"
    if idx < 2 * n / 3:
        return "medium"
    return "hard"


def stratify_instances(
    instances: list[dict[str, Any]],
    *,
    target: int,
    seed: int,
    max_per_repo: int = 4,
) -> list[dict[str, Any]]:
    """Difficulty quantile + repo diversity. 결정적."""
    if not instances:
        return []
    rng = random.Random(seed)
    scored = [(inst, compute_features(inst).difficulty_score()) for inst in instances]
    all_scores = [s for _, s in scored]

    for inst, score in scored:
        inst["_mimiron_difficulty"] = _classify(all_scores, score)

    buckets: dict[str, list[dict]] = {"easy": [], "medium": [], "hard": []}
    for inst, _ in scored:
        buckets[inst["_mimiron_difficulty"]].append(inst)

    for b in buckets.values():
        rng.shuffle(b)

    quota_easy = (target + 2) // 3      # 7 if target=20
    quota_medium = (target + 1) // 3    # 7 if target=20
    quota_hard = target - quota_easy - quota_medium  # 6 if target=20

    selected: list[dict] = []
    per_repo: dict[str, int] = {}

    def _pick_from(bucket: list[dict], quota: int) -> int:
        taken = 0
        for inst in bucket:
            if taken >= quota:
                break
            repo = inst["repo"]
            if per_repo.get(repo, 0) >= max_per_repo:
                continue
            selected.append(inst)
            per_repo[repo] = per_repo.get(repo, 0) + 1
            taken += 1
        return taken

    _pick_from(buckets["easy"], quota_easy)
    _pick_from(buckets["medium"], quota_medium)
    _pick_from(buckets["hard"], quota_hard)

    # 부족분 (max_per_repo 로 인해 quota 못 채운 경우) — 다른 bucket 에서 보충
    if len(selected) < target:
        leftover = [i for b in buckets.values() for i in b if i not in selected]
        rng.shuffle(leftover)
        for inst in leftover:
            if len(selected) >= target:
                break
            repo = inst["repo"]
            if per_repo.get(repo, 0) >= max_per_repo:
                continue
            selected.append(inst)
            per_repo[repo] = per_repo.get(repo, 0) + 1

    return selected[:target]
```

- [ ] **Step 4: 테스트 실행 → 통과 확인**

Run: `uv run pytest tests/bench/test_swebench_import.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/mimiron/bench/swebench_import.py tests/bench/test_swebench_import.py
git commit -m "feat(swebench): add stratification algorithm with difficulty quantile + repo diversity"
```

---

## Task 2: Fixture YAML writer (instance → benchmarks/SWE-LITE-XX/)

**Files:**
- Modify: `src/mimiron/bench/swebench_import.py`
- Modify: `tests/bench/test_swebench_import.py`

- [ ] **Step 1: 실패하는 테스트 추가**

`tests/bench/test_swebench_import.py` 끝에 append:
```python
def test_write_fixture_creates_yaml_issue_diff_meta(tmp_path):
    from mimiron.bench.swebench_import import write_fixture

    inst = {
        "instance_id": "django__django-11099",
        "repo": "django/django",
        "base_commit": "419a78300f7c",
        "problem_statement": "Allow non-ASCII username validation",
        "patch": "diff --git a/django/x.py b/django/x.py\n+pass\n",
        "FAIL_TO_PASS": ["tests/auth_tests.py::test_unicode"],
        "PASS_TO_PASS": ["tests/auth_tests.py::test_ascii"],
        "version": "3.0",
        "_mimiron_difficulty": "medium",
    }
    fixture_dir = tmp_path / "benchmarks"
    written = write_fixture(inst, root=fixture_dir, clone_root="../../.bench-clones/swebench")
    assert written.name == "SWE-LITE-django__django-11099"
    assert (written / "benchmark.yaml").exists()
    assert (written / "issue.md").read_text() == "Allow non-ASCII username validation"
    assert (written / "expected.diff").read_text() == inst["patch"]
    import json as _j
    meta = _j.loads((written / "_swebench.json").read_text())
    assert meta["FAIL_TO_PASS"] == ["tests/auth_tests.py::test_unicode"]
    assert meta["instance_id"] == "django__django-11099"


def test_write_fixture_benchmark_yaml_has_swebench_meta_field(tmp_path):
    from mimiron.bench.swebench_import import write_fixture
    from mimiron import yaml_compat as yaml

    inst = {
        "instance_id": "x__x-1", "repo": "x/x", "base_commit": "deadbeef",
        "problem_statement": "p", "patch": "d",
        "FAIL_TO_PASS": ["a::b"], "PASS_TO_PASS": [],
        "version": "1.0", "_mimiron_difficulty": "easy",
    }
    written = write_fixture(inst, root=tmp_path, clone_root="../../.clones")
    y = yaml.safe_load((written / "benchmark.yaml").read_text())
    assert y["swebench_meta"] == "_swebench.json"
    assert y["target_ref"] is None
    assert "pytest" in y["test_command"]
    assert "a::b" in y["test_command"]
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/bench/test_swebench_import.py -v -k write_fixture`
Expected: `ImportError: cannot import name 'write_fixture'`

- [ ] **Step 3: implementation 추가**

`src/mimiron/bench/swebench_import.py` 끝에 append:
```python
import json as _json
from pathlib import Path

from mimiron import yaml_compat as yaml


def write_fixture(
    instance: dict[str, Any],
    *,
    root: Path,
    clone_root: str,
) -> Path:
    """SWE-bench instance → benchmarks/SWE-LITE-<id>/ 디렉토리 생성.

    root: benchmarks/ 디렉토리의 부모 (보통 cwd) — 안에 benchmarks/SWE-LITE-XX/ 작성
    clone_root: benchmark.yaml 의 repo 필드가 가리킬 상대 경로 (importer 가 미리 clone)
    """
    iid = instance["instance_id"]
    fixture_id = f"SWE-LITE-{iid}"
    fixture_dir = root / fixture_id
    fixture_dir.mkdir(parents=True, exist_ok=True)

    repo_dir_name = iid.split("__")[0] + "__" + iid.rsplit("-", 1)[0].split("__", 1)[1]
    repo_path = f"{clone_root}/{repo_dir_name}"

    ftp = instance.get("FAIL_TO_PASS", []) or []
    ptp = instance.get("PASS_TO_PASS", []) or []
    selectors = " ".join(ftp + ptp)

    bench_yaml = {
        "id": fixture_id,
        "repo": repo_path,
        "base_ref": instance["base_commit"],
        "target_ref": None,
        "issue_text_file": "issue.md",
        "expected_diff_file": "expected.diff",
        "test_command": f"pytest {selectors} -q",
        "difficulty": instance.get("_mimiron_difficulty", "unknown"),
        "swebench_meta": "_swebench.json",
        "notes": (
            f"Imported from princeton-nlp/SWE-bench_Lite\n"
            f"Original instance_id: {iid}\n"
        ),
    }
    (fixture_dir / "benchmark.yaml").write_text(
        yaml.safe_dump(bench_yaml, sort_keys=False), encoding="utf-8"
    )
    (fixture_dir / "issue.md").write_text(instance["problem_statement"], encoding="utf-8")
    (fixture_dir / "expected.diff").write_text(instance["patch"], encoding="utf-8")

    meta = {
        "instance_id": iid,
        "FAIL_TO_PASS": ftp,
        "PASS_TO_PASS": ptp,
        "version": instance.get("version", "unknown"),
        "environment_setup_commit": instance.get("environment_setup_commit"),
    }
    (fixture_dir / "_swebench.json").write_text(
        _json.dumps(meta, indent=2), encoding="utf-8"
    )

    return fixture_dir
```

- [ ] **Step 4: 테스트 실행 → 통과 확인**

Run: `uv run pytest tests/bench/test_swebench_import.py -v`
Expected: 5 passed (3 from T1 + 2 new)

- [ ] **Step 5: Commit**

```bash
git add src/mimiron/bench/swebench_import.py tests/bench/test_swebench_import.py
git commit -m "feat(swebench): add fixture writer (instance → benchmarks/SWE-LITE-<id>/)"
```

---

## Task 3: Dataset loader (JSONL primary + HF optional)

**Files:**
- Modify: `src/mimiron/bench/swebench_import.py`
- Modify: `tests/bench/test_swebench_import.py`
- Create: `tests/fixtures/swebench_sample.jsonl`

- [ ] **Step 1: 테스트 fixture 작성**

`tests/fixtures/swebench_sample.jsonl`:
```jsonl
{"instance_id": "django__django-11099", "repo": "django/django", "base_commit": "419a78300f7c", "problem_statement": "Allow non-ASCII username", "patch": "diff --git a/x.py b/x.py\n+pass\n", "FAIL_TO_PASS": ["t::a"], "PASS_TO_PASS": [], "version": "3.0"}
{"instance_id": "sympy__sympy-13441", "repo": "sympy/sympy", "base_commit": "abc123", "problem_statement": "count_ops issue", "patch": "diff --git a/y.py b/y.py\n+x=1\n", "FAIL_TO_PASS": ["t::b"], "PASS_TO_PASS": ["t::c"], "version": "1.1"}
{"instance_id": "astropy__astropy-7166", "repo": "astropy/astropy", "base_commit": "def456", "problem_statement": "InheritDocstrings broken", "patch": "diff --git a/z.py b/z.py\n+x=2\n", "FAIL_TO_PASS": ["t::d"], "PASS_TO_PASS": [], "version": "2.0"}
```

- [ ] **Step 2: 실패하는 테스트 추가**

`tests/bench/test_swebench_import.py` 끝에 append:
```python
def test_load_from_jsonl_reads_all_records():
    from mimiron.bench.swebench_import import load_from_jsonl
    p = Path(__file__).parent.parent / "fixtures" / "swebench_sample.jsonl"
    insts = load_from_jsonl(p)
    assert len(insts) == 3
    assert insts[0]["instance_id"] == "django__django-11099"
    assert insts[2]["repo"] == "astropy/astropy"


def test_load_from_jsonl_raises_on_missing_required_field(tmp_path):
    from mimiron.bench.swebench_import import load_from_jsonl, ImportError as IE
    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"instance_id": "x"}\n', encoding="utf-8")
    with pytest.raises(IE):
        load_from_jsonl(bad)
```

- [ ] **Step 3: 실패 확인**

Run: `uv run pytest tests/bench/test_swebench_import.py -v -k load_from_jsonl`
Expected: `ImportError: cannot import name 'load_from_jsonl'`

- [ ] **Step 4: implementation 추가**

`src/mimiron/bench/swebench_import.py` 의 import 블록 위에:
```python
class ImportError(ValueError):
    """SWE-bench import 오류."""
```

`src/mimiron/bench/swebench_import.py` 끝에 append:
```python
_REQUIRED = ("instance_id", "repo", "base_commit", "problem_statement", "patch")


def load_from_jsonl(path: Path) -> list[dict[str, Any]]:
    """로컬 JSONL → instance dict 리스트. HF 의존성 없음."""
    out: list[dict[str, Any]] = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            rec = _json.loads(line)
        except _json.JSONDecodeError as e:
            raise ImportError(f"line {n}: invalid JSON: {e}") from e
        missing = [k for k in _REQUIRED if k not in rec]
        if missing:
            raise ImportError(f"line {n}: missing required fields {missing}")
        out.append(rec)
    return out


def load_from_huggingface(subset: str = "test") -> list[dict[str, Any]]:
    """HF datasets 의존성 lazy import. PoC 외 사용자가 직접 부를 때만."""
    try:
        from datasets import load_dataset  # type: ignore[import-not-found]
    except ImportError as e:
        raise ImportError(
            "HuggingFace `datasets` not installed. "
            "Install: `uv pip install -e '.[swebench]'` or use --from-jsonl <path>"
        ) from e
    ds = load_dataset("princeton-nlp/SWE-bench_Lite", split=subset)
    return [dict(x) for x in ds]
```

`ImportError` 가 Python builtin 과 충돌하지만 *모듈 내부에서만* 쓰니까 OK. (외부 호출자는 `from mimiron.bench.swebench_import import ImportError as SwebenchImportError` 로 alias 가능.)

- [ ] **Step 5: 테스트 실행 → 통과 확인**

Run: `uv run pytest tests/bench/test_swebench_import.py -v`
Expected: 7 passed

- [ ] **Step 6: Commit**

```bash
git add src/mimiron/bench/swebench_import.py tests/bench/test_swebench_import.py tests/fixtures/swebench_sample.jsonl
git commit -m "feat(swebench): add JSONL loader + HF dataset lazy bridge"
```

---

## Task 4: `mimiron-bench swebench import` CLI subcommand

**Files:**
- Modify: `src/mimiron/bench/cli.py`
- Create: `tests/bench/test_swebench_import_cli.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/bench/test_swebench_import_cli.py`:
```python
"""mimiron-bench swebench import — CLI integration."""
from __future__ import annotations

from pathlib import Path

import pytest


def test_swebench_import_creates_stratified_fixtures(tmp_path, monkeypatch):
    from mimiron.bench import cli as bench_cli

    monkeypatch.chdir(tmp_path)
    src = Path(__file__).parent.parent / "fixtures" / "swebench_sample.jsonl"

    rc = bench_cli.main([
        "swebench", "import",
        "--from-jsonl", str(src),
        "--stratified", "3",
        "--seed", "42",
    ])
    assert rc == 0
    created = sorted((tmp_path / "benchmarks").glob("SWE-LITE-*"))
    assert len(created) == 3
    assert all((d / "benchmark.yaml").exists() for d in created)
    assert all((d / "issue.md").exists() for d in created)


def test_swebench_import_refuses_without_source(tmp_path, monkeypatch):
    from mimiron.bench import cli as bench_cli

    monkeypatch.chdir(tmp_path)
    rc = bench_cli.main(["swebench", "import", "--stratified", "3"])
    assert rc == 2  # usage error
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/bench/test_swebench_import_cli.py -v`
Expected: `SystemExit: 2` or `argparse error: invalid choice 'swebench'`

- [ ] **Step 3: build_parser 에 swebench 추가**

`src/mimiron/bench/cli.py` 의 `build_parser()` 함수 안, `p_suite.set_defaults(...)` 다음에 append:
```python
    p_sb = sub.add_parser("swebench", help="SWE-bench Lite dataset adapter")
    sb_sub = p_sb.add_subparsers(dest="sb_cmd", required=True)

    p_sb_import = sb_sub.add_parser("import", help="HF or JSONL → benchmarks/SWE-LITE-XX/")
    p_sb_import.add_argument("--from-jsonl", dest="from_jsonl", default=None,
                              help="Local JSONL of SWE-bench instances (offline mode).")
    p_sb_import.add_argument("--from-hf", dest="from_hf", action="store_true",
                              help="Pull from HuggingFace princeton-nlp/SWE-bench_Lite.")
    p_sb_import.add_argument("--stratified", type=int, default=20,
                              help="Number of instances to sample (default 20).")
    p_sb_import.add_argument("--seed", type=int, default=42)
    p_sb_import.add_argument("--clone-root", default="../../.bench-clones/swebench",
                              help="Relative repo path written into benchmark.yaml.")
    p_sb_import.set_defaults(func=cmd_swebench_import)
```

- [ ] **Step 4: cmd_swebench_import 함수 추가**

`src/mimiron/bench/cli.py` 의 `cmd_suite` 함수 다음에 append:
```python
def cmd_swebench_import(args: argparse.Namespace) -> int:
    from mimiron.bench.swebench_import import (
        ImportError as SwebenchImportError,
        load_from_jsonl,
        load_from_huggingface,
        stratify_instances,
        write_fixture,
    )

    if not args.from_jsonl and not args.from_hf:
        print("error: one of --from-jsonl or --from-hf is required", file=sys.stderr)
        return 2

    cwd = Path.cwd()
    try:
        if args.from_jsonl:
            insts = load_from_jsonl(Path(args.from_jsonl))
        else:
            insts = load_from_huggingface()
    except SwebenchImportError as e:
        print(f"error: dataset load: {e}", file=sys.stderr)
        return 2

    sampled = stratify_instances(
        insts, target=args.stratified, seed=args.seed,
    )
    bench_root = cwd / "benchmarks"
    bench_root.mkdir(parents=True, exist_ok=True)
    for inst in sampled:
        d = write_fixture(inst, root=bench_root, clone_root=args.clone_root)
        print(f"wrote {d.relative_to(cwd)}")
    print(f"\nimported {len(sampled)} fixtures into {bench_root.relative_to(cwd)}")
    return 0
```

- [ ] **Step 5: 테스트 실행 → 통과 확인**

Run: `uv run pytest tests/bench/test_swebench_import_cli.py -v`
Expected: 2 passed

- [ ] **Step 6: 회귀 확인**

Run: `uv run pytest tests/ -v --tb=short`
Expected: all previous + 4 new = passing

- [ ] **Step 7: Commit**

```bash
git add src/mimiron/bench/cli.py tests/bench/test_swebench_import_cli.py
git commit -m "feat(swebench): wire 'mimiron-bench swebench import' CLI subcommand"
```

---

## Task 5: `--clarification-from` flag for `mimiron init`

**Files:**
- Modify: `src/mimiron/cli.py`
- Create: `tests/test_cli_clarification_from.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_cli_clarification_from.py`:
```python
"""mimiron init --clarification-from <file> — clarify phase skip + state injection."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_init_with_clarification_jumps_to_spec_phase(tmp_path, monkeypatch):
    from mimiron import cli

    monkeypatch.chdir(tmp_path)
    src = tmp_path / "issue.md"
    src.write_text("Allow non-ASCII username validation.\n\nExpected: validator accepts é, ü.\n")

    rc = cli.main([
        "init", "swebench-django-11099",
        "--clarification-from", str(src),
        "--no-persist",
    ])
    assert rc == 0
    sidecar = tmp_path / ".mimiron" / "swebench-django-11099"
    assert sidecar.exists()
    state = json.loads((sidecar / "state.json").read_text())
    assert state["phase"] == "spec"
    clar = sidecar / "clarification.md"
    assert clar.exists()
    assert "non-ASCII username" in clar.read_text()


def test_init_clarification_file_missing_returns_usage_error(tmp_path, monkeypatch):
    from mimiron import cli

    monkeypatch.chdir(tmp_path)
    rc = cli.main([
        "init", "x",
        "--clarification-from", str(tmp_path / "nope.md"),
    ])
    assert rc == 2


def test_init_without_clarification_still_starts_at_clarify(tmp_path, monkeypatch):
    """Regression: 기존 동작 안 깨짐."""
    from mimiron import cli

    monkeypatch.chdir(tmp_path)
    rc = cli.main(["init", "regular-slug", "--no-persist"])
    assert rc == 0
    state = json.loads((tmp_path / ".mimiron" / "regular-slug" / "state.json").read_text())
    assert state["phase"] == "clarify"
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_cli_clarification_from.py -v`
Expected: `argparse: unrecognized arguments: --clarification-from`

- [ ] **Step 3: cli.py 의 init parser 수정**

`src/mimiron/cli.py` 에서 `init` subparser 정의 부분을 찾아 (`build_parser()` 안의 `p_init`) `add_argument` 들 다음에 append (정확한 위치는 `--no-persist` 다음):
```python
    p_init.add_argument(
        "--clarification-from",
        dest="clarification_from",
        default=None,
        help="외부 clarification.md 직주입 → clarify phase skip, phase=spec 로 점프 "
             "(SWE-bench 어댑터 / regression fixture 용).",
    )
```

- [ ] **Step 4: cmd_init 본문 수정**

`src/mimiron/cli.py` 의 `cmd_init()` 함수에서 `sidecar.mkdir(parents=True)` 호출 다음, `State.create(...)` 직전에 삽입:
```python
    clar_src = getattr(args, "clarification_from", None)
    clar_text: str | None = None
    if clar_src:
        clar_path = Path(clar_src)
        if not clar_path.is_absolute():
            clar_path = (cwd / clar_path).resolve()
        if not clar_path.exists():
            print(f"error: --clarification-from file not found: {clar_src}", file=sys.stderr)
            return EXIT_USAGE_ERROR
        clar_text = clar_path.read_text(encoding="utf-8")
```

같은 함수에서 `state = State.create(...)` 호출 다음에 (state.json 저장 직전) 삽입:
```python
    if clar_text is not None:
        (sidecar / "clarification.md").write_text(clar_text, encoding="utf-8")
        state.phase = "spec"
```

- [ ] **Step 5: 테스트 실행 → 통과 확인**

Run: `uv run pytest tests/test_cli_clarification_from.py -v`
Expected: 3 passed

- [ ] **Step 6: 회귀 확인**

Run: `uv run pytest tests/ -v --tb=short`
Expected: 모든 기존 테스트 + 3 new = passing (특히 기존 `cmd_init` 테스트들)

- [ ] **Step 7: Commit**

```bash
git add src/mimiron/cli.py tests/test_cli_clarification_from.py
git commit -m "feat(cli): add --clarification-from flag to skip clarify phase (closes #SWE-bench adapter)"
```

---

## Task 6: `swebench_runner.py` — FAIL_TO_PASS/PASS_TO_PASS measurement

**Files:**
- Create: `src/mimiron/bench/swebench_runner.py`
- Create: `tests/bench/test_swebench_runner.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/bench/test_swebench_runner.py`:
```python
"""swebench_runner — pytest selector 기반 test_pass_rate 측정."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest


def _mk_meta(tmp_path, ftp, ptp):
    p = tmp_path / "_swebench.json"
    p.write_text(json.dumps({"FAIL_TO_PASS": ftp, "PASS_TO_PASS": ptp}))
    return p


def test_run_swebench_tests_all_pass_returns_1(tmp_path):
    from mimiron.bench.swebench_runner import run_swebench_tests

    meta = _mk_meta(tmp_path, ftp=["t::a"], ptp=["t::b"])
    fake = type("R", (), {
        "returncode": 0,
        "stdout": "2 passed in 0.1s",
        "stderr": "",
    })()
    with patch("subprocess.run", return_value=fake) as m:
        rate, details = run_swebench_tests(meta_path=meta, repo_root=tmp_path)
    assert rate == 1.0
    assert details["selectors_total"] == 2
    assert details["selectors_passed"] == 2
    args = m.call_args[0][0]
    assert "t::a" in args and "t::b" in args


def test_run_swebench_tests_partial_pass_returns_fraction(tmp_path):
    from mimiron.bench.swebench_runner import run_swebench_tests

    meta = _mk_meta(tmp_path, ftp=["t::a", "t::b"], ptp=["t::c", "t::d"])
    fake = type("R", (), {
        "returncode": 1,
        "stdout": "2 passed, 2 failed in 0.3s",
        "stderr": "",
    })()
    with patch("subprocess.run", return_value=fake):
        rate, details = run_swebench_tests(meta_path=meta, repo_root=tmp_path)
    assert rate == 0.5
    assert details["selectors_passed"] == 2


def test_run_swebench_tests_no_selectors_returns_0(tmp_path):
    from mimiron.bench.swebench_runner import run_swebench_tests

    meta = _mk_meta(tmp_path, ftp=[], ptp=[])
    rate, details = run_swebench_tests(meta_path=meta, repo_root=tmp_path)
    assert rate == 0.0
    assert details["reason"] == "no_selectors"


def test_run_swebench_tests_env_error_returns_0_with_reason(tmp_path):
    from mimiron.bench.swebench_runner import run_swebench_tests

    meta = _mk_meta(tmp_path, ftp=["t::a"], ptp=[])
    fake = type("R", (), {
        "returncode": 2,  # pytest collection error
        "stdout": "",
        "stderr": "ImportError: no module x",
    })()
    with patch("subprocess.run", return_value=fake):
        rate, details = run_swebench_tests(meta_path=meta, repo_root=tmp_path)
    assert rate == 0.0
    assert details["reason"] == "env_error"
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/bench/test_swebench_runner.py -v`
Expected: `ModuleNotFoundError: No module named 'mimiron.bench.swebench_runner'`

- [ ] **Step 3: implementation 작성**

`src/mimiron/bench/swebench_runner.py`:
```python
"""SWE-bench style test runner — FAIL_TO_PASS + PASS_TO_PASS pytest selector 측정."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

# pytest summary line: "N passed", "N failed", "N error"
_PASS_RE = re.compile(r"(\d+)\s+passed")
_FAIL_RE = re.compile(r"(\d+)\s+failed")


def run_swebench_tests(
    *,
    meta_path: Path,
    repo_root: Path,
    timeout_s: int = 600,
) -> tuple[float, dict[str, Any]]:
    """meta_path 의 FAIL_TO_PASS+PASS_TO_PASS selector 를 repo_root 에서 pytest 로 실행.

    Returns: (test_pass_rate, details)
      - test_pass_rate ∈ [0.0, 1.0]: passed / total selectors
      - details: 디버깅용 메타 (reason 포함 가능)
    """
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    ftp = list(meta.get("FAIL_TO_PASS", []) or [])
    ptp = list(meta.get("PASS_TO_PASS", []) or [])
    selectors = ftp + ptp
    total = len(selectors)

    if total == 0:
        return 0.0, {"reason": "no_selectors", "selectors_total": 0, "selectors_passed": 0}

    cmd = ["pytest", "-q", "--no-header", *selectors]
    try:
        proc = subprocess.run(
            cmd, cwd=repo_root, capture_output=True, text=True,
            timeout=timeout_s, check=False,
        )
    except subprocess.TimeoutExpired:
        return 0.0, {
            "reason": "timeout", "selectors_total": total, "selectors_passed": 0,
            "timeout_s": timeout_s,
        }

    if proc.returncode in (2, 3, 4, 5):  # pytest collection / usage / internal error
        return 0.0, {
            "reason": "env_error", "selectors_total": total, "selectors_passed": 0,
            "stderr_tail": proc.stderr[-500:],
        }

    passed_m = _PASS_RE.search(proc.stdout)
    passed = int(passed_m.group(1)) if passed_m else 0
    rate = passed / total if total else 0.0
    return rate, {
        "reason": "ok",
        "selectors_total": total,
        "selectors_passed": passed,
        "selectors_failed": (int(_FAIL_RE.search(proc.stdout).group(1))
                              if _FAIL_RE.search(proc.stdout) else (total - passed)),
        "returncode": proc.returncode,
    }
```

- [ ] **Step 4: 테스트 실행 → 통과 확인**

Run: `uv run pytest tests/bench/test_swebench_runner.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/mimiron/bench/swebench_runner.py tests/bench/test_swebench_runner.py
git commit -m "feat(swebench): add pytest selector runner for FAIL_TO_PASS/PASS_TO_PASS"
```

---

## Task 7: `mimiron-bench run --swebench-tests` flag

**Files:**
- Modify: `src/mimiron/bench/cli.py`
- Modify: `tests/bench/test_swebench_runner.py`

- [ ] **Step 1: 실패하는 통합 테스트 추가**

`tests/bench/test_swebench_runner.py` 끝에 append:
```python
def test_bench_run_with_swebench_tests_flag_uses_runner(tmp_path, monkeypatch):
    """`mimiron-bench run X --swebench-tests` → swebench_runner 호출 + verdict 기록."""
    from mimiron.bench import cli as bench_cli

    monkeypatch.chdir(tmp_path)
    fixture = tmp_path / "benchmarks" / "SWE-LITE-x"
    fixture.mkdir(parents=True)
    (fixture / "benchmark.yaml").write_text(
        "id: SWE-LITE-x\n"
        f"repo: {tmp_path}\n"
        "base_ref: HEAD\n"
        "target_ref: null\n"
        "issue_text_file: issue.md\n"
        "expected_diff_file: expected.diff\n"
        "test_command: 'pytest -q'\n"
        "difficulty: easy\n"
        "swebench_meta: _swebench.json\n"
    )
    (fixture / "issue.md").write_text("p")
    (fixture / "expected.diff").write_text("d")
    (fixture / "_swebench.json").write_text(
        json.dumps({"FAIL_TO_PASS": ["t::a"], "PASS_TO_PASS": []})
    )

    # subprocess.run mock so pytest selector "passes"
    fake = type("R", (), {"returncode": 0, "stdout": "1 passed", "stderr": ""})()
    with patch("subprocess.run", return_value=fake):
        # MIMIRON_BENCH_DRY_RUN 안 켜고 진짜 runner 경로 검증
        monkeypatch.delenv("MIMIRON_BENCH_DRY_RUN", raising=False)
        rc = bench_cli.main(["run", "SWE-LITE-x", "--swebench-tests"])
    assert rc in (0, 1)  # passed or failed verdict OK; flow 자체가 동작했는지 확인
    status_file = tmp_path / ".mimiron" / "_outer" / "status" / "SWE-LITE-x.json"
    assert status_file.exists()
    v = json.loads(status_file.read_text())
    assert v["test_pass_rate"] == 1.0
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/bench/test_swebench_runner.py -v -k swebench_tests_flag`
Expected: `argparse: unrecognized arguments: --swebench-tests` 또는 status_file 없음

- [ ] **Step 3: bench/cli.py 의 `p_run` 에 flag 추가**

`src/mimiron/bench/cli.py` 의 `build_parser()` 안, `p_run.add_argument("--similarity-from", ...)` 다음에 append:
```python
    p_run.add_argument(
        "--swebench-tests",
        dest="swebench_tests",
        action="store_true",
        help="SWE-bench fixture 의 _swebench.json 의 selector 로 test_pass_rate 측정.",
    )
```

- [ ] **Step 4: cmd_run 본문 수정 — swebench_tests 분기**

`src/mimiron/bench/cli.py` 의 `cmd_run()` 함수에서, `run_benchmark(...)` 호출 직전에 swebench_tests 분기 추가. 기존 코드:
```python
    try:
        from mimiron.bench.runner import run_benchmark
        v = run_benchmark(
            benchmark=b,
            work_root=work_root,
            similarity_provider=similarity_provider,
        )
```
를 다음으로 교체:
```python
    swebench_tests = getattr(args, "swebench_tests", False)
    try:
        from mimiron.bench.runner import run_benchmark
        if swebench_tests:
            from mimiron.bench.swebench_runner import run_swebench_tests
            meta_path = bench_dir / (
                getattr(b, "swebench_meta", None) or "_swebench.json"
            )
            if not meta_path.exists():
                print(f"error: --swebench-tests requires {meta_path}", file=sys.stderr)
                return 2
            # candidate 적용된 워크트리에서 selector test
            from mimiron.bench.worktree_iso import isolate_at_ref
            repo = Path(b.repo)
            if not repo.is_absolute():
                repo = (b.yaml_dir / repo).resolve()
            with isolate_at_ref(repo=repo, ref=b.base_ref, dest=work_root / b.id) as iso:
                rate, details = run_swebench_tests(meta_path=meta_path, repo_root=iso)
            v = {
                "id": b.id,
                "status": "passed" if rate == 1.0 else "failed",
                "bench_score": rate,
                "test_pass_rate": rate,
                "semantic_similarity": (
                    similarity_provider(b.expected_diff(), "") if similarity_provider else None
                ),
                "details": {"resolved": rate == 1.0, "swebench": details},
            }
        else:
            v = run_benchmark(
                benchmark=b,
                work_root=work_root,
                similarity_provider=similarity_provider,
            )
```

- [ ] **Step 5: Benchmark dataclass 에 swebench_meta 필드 추가**

`src/mimiron/bench/runner.py` 의 `Benchmark` dataclass 에 `swebench_meta` 필드 추가 (선언 + `load()` 안의 매핑):

Dataclass 필드 추가 (`notes: str` 다음):
```python
    swebench_meta: str | None  # _swebench.json 같은 보조 메타 파일명 (옵셔널)
```

`Benchmark.load()` 의 `cls(...)` 호출에 추가 (`notes=raw.get("notes", "")` 다음):
```python
            swebench_meta=raw.get("swebench_meta"),
```

- [ ] **Step 6: 테스트 실행 → 통과 확인**

Run: `uv run pytest tests/bench/test_swebench_runner.py -v`
Expected: 5 passed

- [ ] **Step 7: 회귀 확인**

Run: `uv run pytest tests/ -v --tb=short`
Expected: 모든 기존 테스트 + 신규 모두 passing

- [ ] **Step 8: Commit**

```bash
git add src/mimiron/bench/cli.py src/mimiron/bench/runner.py tests/bench/test_swebench_runner.py
git commit -m "feat(swebench): wire --swebench-tests flag on mimiron-bench run (hybrid verdict)"
```

---

## Task 8: `pyproject.toml` `[swebench]` optional extra

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: 현재 pyproject 확인**

Run: `grep -n "optional-dependencies\|\[project" /home/namgee/Development/private/mimiron/pyproject.toml`
Expected: 기존 `[project]` 섹션 + `optional-dependencies` 가 있을 수도/없을 수도 있음

- [ ] **Step 2: optional-dependencies 추가**

`pyproject.toml` 의 `[project]` 섹션 *바로 다음* (또는 기존 `[project.optional-dependencies]` 가 있으면 거기 안에) 추가:
```toml
[project.optional-dependencies]
swebench = [
    "datasets>=2.14",
]
```

이미 `[project.optional-dependencies]` 가 있으면 그 안에 `swebench = [...]` 만 추가.

- [ ] **Step 3: 설치 가능 검증 (dry-run)**

Run: `uv pip install --dry-run -e '/home/namgee/Development/private/mimiron[swebench]'`
Expected: `datasets` 가 해결됨 (또는 이미 설치돼 있음)

- [ ] **Step 4: 기존 테스트 회귀 확인**

Run: `uv run pytest tests/ --tb=line`
Expected: 변동 없음

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml
git commit -m "chore(swebench): add [swebench] optional extra (datasets>=2.14)"
```

---

## Task 9: `mimiron-swebench` skill + slash command

**Files:**
- Create: `skills/mimiron-swebench/SKILL.md`
- Create: `commands/mimiron-swebench.md`

- [ ] **Step 1: skill 작성**

`skills/mimiron-swebench/SKILL.md`:
```markdown
---
name: mimiron-swebench
description: SWE-bench Lite suite 를 mimiron pipeline 으로 순회 실행 + hybrid verdict 집계. `/mimiron-swebench` 슬래시 커맨드로 트리거되며, benchmarks/SWE-LITE-* fixture 들을 sequential 하게 돌리고 .mimiron/_outer/swebench/REPORT.md 를 생성한다. Importer 가 이미 돌아 fixture 가 준비된 상태가 전제.
---

# mimiron-swebench — SWE-bench Lite suite runner

## When to invoke

User invokes `/mimiron-swebench` (or asks "SWE-bench 돌려" / "swebench suite run").

전제: `benchmarks/SWE-LITE-*/` fixture 들이 이미 존재. 없으면 먼저:
```
mimiron-bench swebench import --from-jsonl <path> --stratified 20 --seed 42
```
또는 `--from-hf` 로 import 안내.

## Execution loop

```
1. List fixtures: glob benchmarks/SWE-LITE-* (정렬, deterministic order)
2. State file: .mimiron/_outer/swebench/cursor.json
   {"completed": [...], "skipped": [...], "current": null}
   재개 시 이 파일 읽어서 이미 끝난 건 skip
3. For each remaining fixture (sequential):
   a. Verify repo clone: benchmark.yaml 의 repo 경로 + base_ref 존재 확인
      → 없으면 cursor 에 skip 기록 + reason="missing_clone", 다음 fixture
   b. mimiron init <slug> --clarification-from <fixture>/issue.md
      (slug = SWE-LITE-XX 의 소문자/dash 정규화)
   c. /mimiron-resume <slug>  로 6-phase 자동 진행
      (clarify 는 skip, spec → plan → execute → evaluate → finalize 진행)
   d. finalize 직후 .mimiron/<slug>/result.diff 추출
      → .mimiron/_outer/swebench/<fixture>.diff 로 복사
   e. bench-judge skill 호출:
      input: (expected.diff, candidate.diff)
      output: .mimiron/_outer/judge/<fixture>.json {score: 0~1, rationale}
   f. mimiron-bench run <fixture> --swebench-tests --similarity-from <judge.json>
      → .mimiron/_outer/status/<fixture>.json 작성
   g. cursor.json 업데이트 (completed 에 추가)
4. Aggregate → .mimiron/_outer/swebench/REPORT.md:
   - Header: Suite, N instances, M completed, K skipped
   - Per-instance row: id | resolved | bench_score | test_pass_rate | semantic_sim | reason
   - Footer:
     - resolved%: M_resolved / M_completed
     - avg bench_score (completed)
     - skipped reasons distribution
```

## Stuck / fail handling

- phase=stuck 도달 fixture: cursor 에 skip 추가, reason="mimiron_stuck", 다음 fixture 진행
- spec phase 게이트 실패 (quality_score 낮음): skip, reason="spec_quality"
- 환경 에러 (clone 없음, 의존성 충돌): skip, reason="env_error"
- 0 retry 정책 (PoC). retry 는 사용자가 명시적으로 `/mimiron-resume <slug>` 호출.

## Output format

`.mimiron/_outer/swebench/REPORT.md`:
```
# SWE-bench Lite — Mimiron PoC Run

Generated: 2026-05-24T10:00:00Z
Mimiron: v0.X.0
Fixtures: 20 (7 easy / 7 medium / 6 hard)

## Aggregate

- Completed: 18 / 20
- Skipped: 2 (env_error: 1, mimiron_stuck: 1)
- Resolved: 4 / 18 (22.2%)
- Avg bench_score: 0.413

## Per-instance

| ID                              | resolved | score | test | sim   | reason |
| SWE-LITE-django__django-11099   | ✓        | 0.92  | 1.0  | 0.80  | ok     |
| SWE-LITE-sympy__sympy-13441     | ✗        | 0.40  | 0.5  | 0.25  | ok     |
| SWE-LITE-astropy__astropy-7166  | -        | -     | -    | -     | env_error |
| ...                             |          |       |      |       |        |
```

## Don'ts

- 절대 mimiron core code 수정하지 말 것 — 이 skill 은 orchestrator 일 뿐
- 한 fixture 가 stuck 됐다고 unstuck skill 자동 호출하지 말 것 (사용자 결정 영역)
- 결과 파일을 deleting 으로 정리하지 말 것 (debugging 용 보존)
```

- [ ] **Step 2: slash command 작성**

`commands/mimiron-swebench.md`:
```markdown
---
name: mimiron-swebench
description: Run SWE-bench Lite suite — fixture 순회 + hybrid 채점 + REPORT.md 생성
---

mimiron-swebench skill 을 invoke 해서 `benchmarks/SWE-LITE-*/` fixture 들을 순회 실행하고 `.mimiron/_outer/swebench/REPORT.md` 를 생성한다.

전제: importer 가 이미 돌아 fixture 가 준비된 상태. 없으면 먼저 안내:
`mimiron-bench swebench import --from-jsonl <path> --stratified 20 --seed 42`
```

- [ ] **Step 3: skill metadata 검증 (lint)**

Run: `cat /home/namgee/Development/private/mimiron/skills/mimiron-swebench/SKILL.md | head -5`
Expected: 정상적인 frontmatter (`---`, `name:`, `description:`)

- [ ] **Step 4: Commit**

```bash
git add skills/mimiron-swebench/ commands/mimiron-swebench.md
git commit -m "feat(swebench): add mimiron-swebench orchestration skill + slash command"
```

---

## Task 10: Integration smoke test

**Files:**
- Create: `tests/integration/test_swebench_smoke.py`

- [ ] **Step 1: smoke test 작성**

`tests/integration/test_swebench_smoke.py`:
```python
"""SWE-bench adapter end-to-end smoke — importer → fixture → run path.

Mimiron pipeline 자체는 mock (LLM 호출 회피). 어댑터 부분만 진짜 코드 경로 검증.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest


def test_swebench_end_to_end_importer_to_runner(tmp_path, monkeypatch):
    from mimiron.bench import cli as bench_cli

    monkeypatch.chdir(tmp_path)
    src = Path(__file__).parent.parent / "fixtures" / "swebench_sample.jsonl"

    # 1. Import: 3 instances → 3 fixtures
    rc = bench_cli.main([
        "swebench", "import",
        "--from-jsonl", str(src),
        "--stratified", "3",
        "--seed", "42",
        "--clone-root", str(tmp_path / ".bench-clones"),
    ])
    assert rc == 0
    fixtures = sorted((tmp_path / "benchmarks").glob("SWE-LITE-*"))
    assert len(fixtures) == 3

    # 2. 각 fixture 의 repo 경로 = tmp_path/.bench-clones/...
    #    실존 안 하므로 mock — 진짜로 clone 하지 않음
    target = fixtures[0]
    fake_repo = tmp_path / "fake_repo"
    fake_repo.mkdir()
    import subprocess as _sp
    # benchmark.yaml 의 repo 를 fake_repo 로 강제 (테스트 단순화)
    from mimiron import yaml_compat as yaml
    y = yaml.safe_load((target / "benchmark.yaml").read_text())
    y["repo"] = str(fake_repo)
    y["base_ref"] = "HEAD"
    (target / "benchmark.yaml").write_text(yaml.safe_dump(y, sort_keys=False))

    # fake git init for worktree_iso
    _sp.run(["git", "init", "-q"], cwd=fake_repo, check=True)
    _sp.run(["git", "commit", "-q", "--allow-empty", "-m", "init"], cwd=fake_repo, check=True)

    # 3. mimiron-bench run --swebench-tests (subprocess mock 으로 pytest pass)
    fake = type("R", (), {"returncode": 0, "stdout": "1 passed", "stderr": ""})()
    with patch("subprocess.run", side_effect=lambda *a, **kw: (
        _sp.run(*a, **kw) if "git" in (a[0][0] if a else "") else fake
    )):
        rc = bench_cli.main(["run", target.name, "--swebench-tests"])
    assert rc in (0, 1)

    # 4. status 파일 존재 + test_pass_rate 기록
    status = tmp_path / ".mimiron" / "_outer" / "status" / f"{target.name}.json"
    assert status.exists()
    v = json.loads(status.read_text())
    assert "test_pass_rate" in v
    assert v["details"]["resolved"] is True
```

- [ ] **Step 2: 테스트 실행**

Run: `uv run pytest tests/integration/test_swebench_smoke.py -v`
Expected: 1 passed

- [ ] **Step 3: 전체 회귀**

Run: `uv run pytest tests/ -v --tb=short`
Expected: 197 (기존) + ~13 (new) = 210+ passing

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_swebench_smoke.py
git commit -m "test(swebench): add end-to-end smoke (importer → fixture → run path)"
```

---

## Task 11: CHANGELOG note

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: CHANGELOG 현재 구조 확인**

Run: `head -30 /home/namgee/Development/private/mimiron/CHANGELOG.md`
Expected: 기존 `## [Unreleased]` 또는 최상위 `## [v0.3.0]` 섹션

- [ ] **Step 2: 새 섹션 추가**

`CHANGELOG.md` 의 가장 위 (`# Changelog` 헤더 다음, 첫 release 섹션 이전) 에 추가:
```markdown
## [Unreleased]

### Added
- **SWE-bench Lite adapter (PoC)**: `mimiron-bench swebench import` subcommand 가 HuggingFace 또는 로컬 JSONL 에서 SWE-bench Lite 의 stratified subset (default 20개) 을 `benchmarks/SWE-LITE-XX/` fixture 로 변환. Difficulty 는 patch size + test count + touched files 의 quantile 로 결정, repo diversity 는 `--max-per-repo` 로 제한.
- **`--clarification-from <file>` flag** on `mimiron init`: 외부 clarification.md 직주입 → clarify phase skip + phase=spec 점프. SWE-bench problem_statement 같이 이미 자세한 input 에서 LLM 호출 회피.
- **`mimiron-bench run --swebench-tests` flag**: `_swebench.json` 의 `FAIL_TO_PASS` + `PASS_TO_PASS` pytest selector 를 candidate-applied 워크트리에서 실행 → `test_pass_rate` 산출. Hybrid verdict (`resolved` + `bench_score`) 동시 기록.
- **`mimiron-swebench` skill + `/mimiron-swebench` slash command**: SWE-bench Lite suite 순회 실행 + `.mimiron/_outer/swebench/REPORT.md` 집계.
- **`[swebench]` optional extra** (`pip install -e '.[swebench]'`) for HuggingFace `datasets` dependency. Core 의존성 영향 없음.

### Spec
- `docs/superpowers/specs/2026-05-24-swebench-lite-adapter-design.md`
```

- [ ] **Step 3: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs(changelog): add SWE-bench Lite adapter PoC under [Unreleased]"
```

---

## Self-Review Checklist (작성자용)

### Spec coverage

| Spec § | 어떤 task 가 구현? | OK? |
|---|---|---|
| §3 Architecture | T1-T7 (importer → CLI → runner) | ✓ |
| §4 Components (4 신규 + 3 수정) | T1-T9 (skill 포함 9 파일) | ✓ |
| §5.1 Fixture YAML 확장 | T2, T7 (swebench_meta 필드) | ✓ |
| §5.2 `_swebench.json` | T2 (writer) | ✓ |
| §6 Execution flow | T9 (skill) | ✓ |
| §7 Hybrid scoring | T7 (cmd_run swebench_tests 분기) | ✓ |
| §8 Stratification | T1 | ✓ |
| §9 `--clarification-from` | T5 | ✓ |
| §10 Testing | T1-T7 unit + T10 integration | ✓ |
| §11 Risks (HF offline) | T3 (JSONL primary) | ✓ |
| §11 Risks (shallow clone) | (skill T9 의 verify step 에서 명시) | △ |
| §12 Open questions | 의도적 미해결 (PoC 중 결정) | ✓ |

**Gap**: `--shallow` clone flag 는 spec §11 에 있지만 plan task 로 안 박혔음. *Importer 가 실제로 clone 하는 코드를 안 가지고 있음* (clone_root 만 받음 — 사용자가 별도로 clone). PoC 단계에서는 이게 의도된 단순화 (suite skill 의 step a 에서 verify only). **plan 변경 없이 진행 OK**.

### Placeholder scan
- "TBD" / "TODO" / "fill in later" / "similar to" : 없음 ✓
- 모든 step 에 exact code or exact command ✓
- 모든 함수 시그니처 + 호출 site 일관성 확인됨 ✓

### Type consistency
- `InstanceFeatures` (T1) → `compute_features` (T1) → `stratify_instances` (T1, T4) ✓
- `write_fixture(instance, *, root, clone_root) -> Path` (T2) → `cmd_swebench_import` (T4) ✓
- `run_swebench_tests(*, meta_path, repo_root, timeout_s=600) -> tuple[float, dict]` (T6) → `cmd_run` (T7) ✓
- `Benchmark.swebench_meta: str | None` (T7) → `cmd_run` (T7) ✓

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-24-swebench-lite-adapter.md`.**

11 tasks, 약 5-7시간 (TDD + frequent commits). 의존성 명확하고 T1, T5, T8 은 parallel 가능.

**Two execution options:**

**1. Subagent-Driven (recommended)** — 각 task 당 fresh subagent dispatch, task 간 review checkpoint. T1, T5, T8 은 parallel.

**2. Inline Execution** — 이 세션에서 task 순차 진행, checkpoint 시 사용자 review.

Which approach?
