"""bench scoring 공식."""
from mimiron.bench.scorer import (
    DEFAULT_SIM_GATE,
    compute_bench_score,
    decide_verdict,
    parse_pytest_output,
    parse_generic_test_output,
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


# v0.3.0 #20 — decide_verdict + sim_gate


def test_decide_verdict_passes_when_above_cutoff_and_sim_above_gate() -> None:
    v = decide_verdict(
        bench_score=0.80, semantic_similarity=0.7, cutoff=0.75, sim_gate=0.5
    )
    assert v == "passed"


def test_decide_verdict_fails_when_below_cutoff() -> None:
    v = decide_verdict(
        bench_score=0.50, semantic_similarity=0.7, cutoff=0.75, sim_gate=0.5
    )
    assert v == "failed"


def test_decide_verdict_sim_gate_forces_failed_even_when_score_passes() -> None:
    # B02 NameError regression scenario — test_pass dominates score but sim is low
    v = decide_verdict(
        bench_score=0.76, semantic_similarity=0.32, cutoff=0.75, sim_gate=0.5
    )
    assert v == "failed"


def test_decide_verdict_sim_gate_disabled_when_zero() -> None:
    v = decide_verdict(
        bench_score=0.76, semantic_similarity=0.0, cutoff=0.75, sim_gate=0.0
    )
    assert v == "passed"


def test_decide_verdict_default_sim_gate_is_half() -> None:
    assert DEFAULT_SIM_GATE == 0.5
    # confirm default is applied when sim_gate omitted
    v = decide_verdict(bench_score=0.80, semantic_similarity=0.49, cutoff=0.75)
    assert v == "failed"


def test_decide_verdict_boundary_at_sim_gate_passes() -> None:
    # exactly at sim_gate is allowed through (>=, not >)
    v = decide_verdict(
        bench_score=0.80, semantic_similarity=0.5, cutoff=0.75, sim_gate=0.5
    )
    assert v == "passed"
