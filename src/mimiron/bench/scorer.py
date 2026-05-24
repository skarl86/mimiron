"""bench 점수 공식."""
from __future__ import annotations

import re


DEFAULT_SIM_GATE = 0.5
"""v0.3.0 #20: semantic_similarity 최저선. 이 값 미만이면 bench_score 와 무관하게 verdict='failed'."""


def compute_bench_score(
    *,
    test_pass_rate: float | None,
    semantic_similarity: float,
    w_test: float,
    w_sim: float,
) -> float:
    if test_pass_rate is None:
        # 테스트 없는 PR: w_test=0, w_sim=1.0로 재정규화
        return semantic_similarity
    total = w_test + w_sim
    return (test_pass_rate * w_test + semantic_similarity * w_sim) / total


def decide_verdict(
    *,
    bench_score: float,
    semantic_similarity: float,
    cutoff: float,
    sim_gate: float = DEFAULT_SIM_GATE,
) -> str:
    """v0.3.0 #20: bench_score + sim_gate 로 verdict 결정.

    sim_gate 미만의 candidate 는 *bench_score 와 무관하게* failed. 이는 test_pass_rate 가
    target_ref 큐레이션 보장으로 인해 항상 ~1.0 에 수렴하면서 wild-guess candidate 도
    cutoff 를 넘어 'passed' 로 분류되던 문제 (dogfood/005 §"가장 중요한 시그널") 를 해소.

    cutoff 만 통과한 high-test/low-sim candidate 는 의미적으로 expected 와 무관하므로 게이트.
    """
    if semantic_similarity < sim_gate:
        return "failed"
    return "passed" if bench_score >= cutoff else "failed"


_PYTEST_RESULT = re.compile(r"(?:(\d+) failed,?\s*)?(?:(\d+) passed)")


def parse_pytest_output(stdout: str) -> float | None:
    """pytest 마지막 줄에서 passed/failed 카운트 추출. 못 찾으면 None."""
    m = _PYTEST_RESULT.search(stdout)
    if not m:
        return None
    failed = int(m.group(1)) if m.group(1) else 0
    passed = int(m.group(2)) if m.group(2) else 0
    total = failed + passed
    if total == 0:
        return None
    return passed / total


def parse_generic_test_output(
    *, stdout: str, stderr: str, returncode: int
) -> float:
    """pytest가 아닌 일반 test_command: returncode 기준 binary."""
    return 1.0 if returncode == 0 else 0.0
