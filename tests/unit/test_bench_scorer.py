"""bench scoring 공식."""
from mimiron.bench.scorer import (
    compute_bench_score, parse_pytest_output, parse_generic_test_output
)


def test_compute_bench_score_weighted() -> None:
    # w_test=0.6, w_sim=0.4 → 1.0*0.6 + 0.5*0.4 = 0.8
    s = compute_bench_score(
        test_pass_rate=1.0, semantic_similarity=0.5, w_test=0.6, w_sim=0.4
    )
    assert abs(s - 0.8) < 1e-9


def test_compute_bench_score_renormalizes_when_no_tests() -> None:
    # test_pass_rate=None → w_test=0, w_sim=1.0
    s = compute_bench_score(
        test_pass_rate=None, semantic_similarity=0.9, w_test=0.6, w_sim=0.4
    )
    assert abs(s - 0.9) < 1e-9


def test_parse_pytest_output_simple() -> None:
    out = "============================== 3 passed in 0.10s =============================="
    rate = parse_pytest_output(out)
    assert rate == 1.0


def test_parse_pytest_output_mixed() -> None:
    out = "2 failed, 3 passed in 0.5s"
    rate = parse_pytest_output(out)
    assert rate is not None
    assert abs(rate - 3 / 5) < 1e-6


def test_parse_generic_pass_when_returncode_zero() -> None:
    rate = parse_generic_test_output(stdout="ok", stderr="", returncode=0)
    assert rate == 1.0


def test_parse_generic_fail_when_returncode_nonzero() -> None:
    rate = parse_generic_test_output(stdout="", stderr="err", returncode=1)
    assert rate == 0.0
