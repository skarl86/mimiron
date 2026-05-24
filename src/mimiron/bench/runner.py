"""bench runner — 단일 case 실행 + verdict 산출."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, TypedDict

from mimiron import yaml_compat as yaml


class BenchmarkError(ValueError):
    """Benchmark fixture 오류."""


@dataclass
class Benchmark:
    id: str
    repo: str
    base_ref: str
    target_ref: str
    issue_text_file: str
    expected_diff_file: str
    test_command: str
    difficulty: str
    notes: str
    yaml_dir: Path  # benchmark.yaml의 디렉토리 (relative 경로 해석용)
    swebench_meta: str | None = None  # _swebench.json 같은 보조 메타 파일명 (옵셔널)

    @classmethod
    def load(cls, path: Path) -> "Benchmark":
        raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        required = [
            "id", "repo", "base_ref", "target_ref",
            "issue_text_file", "expected_diff_file", "test_command",
        ]
        for k in required:
            if k not in raw:
                raise BenchmarkError(f"missing required field {k!r}")
        return cls(
            id=raw["id"],
            repo=raw["repo"],
            base_ref=raw["base_ref"],
            target_ref=raw["target_ref"],
            issue_text_file=raw["issue_text_file"],
            expected_diff_file=raw["expected_diff_file"],
            test_command=raw["test_command"],
            difficulty=raw.get("difficulty", "unknown"),
            notes=raw.get("notes", ""),
            yaml_dir=path.parent,
            swebench_meta=raw.get("swebench_meta"),
        )

    def issue_text(self) -> str:
        return (self.yaml_dir / self.issue_text_file).read_text(encoding="utf-8")

    def expected_diff(self) -> str:
        return (self.yaml_dir / self.expected_diff_file).read_text(encoding="utf-8")


class BenchVerdict(TypedDict):
    id: str
    status: str  # "passed" | "failed" | "deferred"
    bench_score: float | None
    test_pass_rate: float | None
    semantic_similarity: float | None
    details: dict[str, Any]


SimilarityProvider = Callable[[str, str], float]


_CANDIDATE_DIFF_FILENAME = "mimiron_output.diff"


def _find_candidate_diff(*, work_root: Path, bench_id: str) -> Path | None:
    """후보 diff 파일을 우선순위로 탐색 (v0.3.0 #20 + #24 per-bench 경로).

    1. `<work_root>/_input/<bench_id>.diff`  — 신규 권장 (per-bench 분리)
    2. `<work_root>/<bench_id>/mimiron_output.diff` — dogfood/005 컨벤션
    3. `<work_root>/../<filename>` — legacy global (deprecated, single-bench 호환)
    """
    candidates = [
        work_root / "_input" / f"{bench_id}.diff",
        work_root / bench_id / _CANDIDATE_DIFF_FILENAME,
        work_root.parent / _CANDIDATE_DIFF_FILENAME,
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def _run_test_command(test_command: str, cwd: Path) -> float:
    """test_command 실행 → test_pass_rate 산출."""
    from mimiron.bench.scorer import parse_pytest_output, parse_generic_test_output

    proc = subprocess.run(
        test_command,
        shell=True,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    rate = parse_pytest_output(proc.stdout)
    if rate is None:
        rate = parse_generic_test_output(
            stdout=proc.stdout, stderr=proc.stderr, returncode=proc.returncode
        )
    return rate


def run_benchmark(
    *,
    benchmark: Benchmark,
    work_root: Path,
    w_test: float = 0.6,
    w_sim: float = 0.4,
    similarity_provider: SimilarityProvider | None = None,
    cutoff: float = 0.75,
    sim_gate: float | None = None,
) -> BenchVerdict:
    """단일 케이스 실행. v0 manual mode에서는 mimiron pipeline 실행은
    *외부*(skill)가 담당하고, 본 함수는 *결과 비교*만 수행.

    v0.3.0 #20 부터: similarity_provider 가 설정되면 test_pass_rate 는 *candidate-applied*
    워크트리에서 측정 (base_ref + candidate.diff). similarity_provider 가 None 이면
    target_ref 측정 (deferred 모드, 기존 호환). candidate diff 가 없거나 apply 실패 시
    test_pass_rate = 0.0. 추가로 `sim < sim_gate` 면 verdict='failed' 강제.

    similarity_provider: Optional[Callable[[str, str], float]] — Mimiron diff와 expected diff를 받아 0~1.
                         None이면 semantic_similarity 미산출 → deferred.
    sim_gate: None 이면 DEFAULT_SIM_GATE (0.5) 사용. 0.0 이면 게이트 비활성.
    """
    from mimiron.bench.scorer import (
        DEFAULT_SIM_GATE,
        compute_bench_score,
        decide_verdict,
    )
    from mimiron.bench.worktree_iso import isolate_at_ref

    repo = Path(benchmark.repo)
    if not repo.is_absolute():
        repo = (benchmark.yaml_dir / repo).resolve()
    iso_dest = work_root / benchmark.id
    if sim_gate is None:
        sim_gate = DEFAULT_SIM_GATE

    # Deferred mode: 기존 호환 — target_ref 워크트리에서 test 측정, sim 없이 반환.
    if similarity_provider is None:
        with isolate_at_ref(repo=repo, ref=benchmark.target_ref, dest=iso_dest) as iso:
            rate = _run_test_command(benchmark.test_command, iso)
        return BenchVerdict(
            id=benchmark.id,
            status="deferred",
            bench_score=None,
            test_pass_rate=rate,
            semantic_similarity=None,
            details={
                "reason": "similarity_provider not set; manual mode",
                "test_measurement_mode": "target-ref",
            },
        )

    # Candidate-applied mode (#20): base_ref 워크트리에 candidate diff 적용 후 test.
    candidate_path = _find_candidate_diff(work_root=work_root, bench_id=benchmark.id)
    actual = ""
    apply_status = "no-candidate"
    rate = 0.0
    with isolate_at_ref(repo=repo, ref=benchmark.base_ref, dest=iso_dest) as iso:
        if candidate_path is not None:
            actual = candidate_path.read_text(encoding="utf-8")
            apply_proc = subprocess.run(
                ["git", "apply", str(candidate_path)],
                cwd=iso,
                capture_output=True,
                text=True,
                check=False,
            )
            if apply_proc.returncode == 0:
                apply_status = "applied"
                rate = _run_test_command(benchmark.test_command, iso)
            else:
                apply_status = "apply-failed"
                # rate stays 0.0
        # else: no candidate found, rate stays 0.0

    expected = benchmark.expected_diff()
    sim = similarity_provider(actual, expected)
    score = compute_bench_score(
        test_pass_rate=rate, semantic_similarity=sim, w_test=w_test, w_sim=w_sim
    )
    verdict = decide_verdict(
        bench_score=score, semantic_similarity=sim, cutoff=cutoff, sim_gate=sim_gate
    )
    return BenchVerdict(
        id=benchmark.id,
        status=verdict,
        bench_score=score,
        test_pass_rate=rate,
        semantic_similarity=sim,
        details={
            "test_measurement_mode": "candidate-applied",
            "candidate_apply_status": apply_status,
            "candidate_path": str(candidate_path) if candidate_path else None,
            "sim_gate": sim_gate,
        },
    )
