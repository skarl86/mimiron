"""bench 점수 공식."""
from __future__ import annotations

import re


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
