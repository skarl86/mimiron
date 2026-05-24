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


def run_benchmark(
    *,
    benchmark: Benchmark,
    work_root: Path,
    w_test: float = 0.6,
    w_sim: float = 0.4,
    similarity_provider: SimilarityProvider | None = None,
    cutoff: float = 0.75,
) -> BenchVerdict:
    """단일 케이스 실행. v0 manual mode에서는 mimiron pipeline 실행은
    *외부*(skill)가 담당하고, 본 함수는 *결과 비교*만 수행.

    similarity_provider: Optional[Callable[[str, str], float]] — Mimiron diff와 expected diff를 받아 0~1.
                         None이면 semantic_similarity 미산출 → deferred.
    """
    from mimiron.bench.scorer import (
        compute_bench_score,
        parse_pytest_output,
        parse_generic_test_output,
    )
    from mimiron.bench.worktree_iso import isolate_at_ref

    repo = Path(benchmark.repo)
    if not repo.is_absolute():
        repo = (benchmark.yaml_dir / repo).resolve()
    iso_dest = work_root / benchmark.id
    # test 실행 (target_ref 워크트리에서 — 원본 결과 검증용)
    with isolate_at_ref(repo=repo, ref=benchmark.target_ref, dest=iso_dest) as iso:
        proc = subprocess.run(
            benchmark.test_command,
            shell=True,
            cwd=iso,
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
    if similarity_provider is None:
        return BenchVerdict(
            id=benchmark.id,
            status="deferred",
            bench_score=None,
            test_pass_rate=rate,
            semantic_similarity=None,
            details={"reason": "similarity_provider not set; manual mode"},
        )
    expected = benchmark.expected_diff()
    diff_file = work_root.parent / "mimiron_output.diff"
    actual = diff_file.read_text(encoding="utf-8") if diff_file.exists() else ""
    sim = similarity_provider(actual, expected)
    score = compute_bench_score(
        test_pass_rate=rate, semantic_similarity=sim, w_test=w_test, w_sim=w_sim
    )
    return BenchVerdict(
        id=benchmark.id,
        status="passed" if score >= cutoff else "failed",
        bench_score=score,
        test_pass_rate=rate,
        semantic_similarity=sim,
        details={"target_ref_tests_passed": rate},
    )
