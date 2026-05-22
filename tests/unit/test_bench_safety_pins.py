"""outer-loop 메타 안전핀."""
from mimiron.bench.suite import compute_halt_signal, HaltReason


def test_halt_when_iteration_cap_reached() -> None:
    s = compute_halt_signal(
        iteration=30,
        aggregate_history=[0.5] * 10,
        iteration_cap=30,
        asymptote_window=5,
        asymptote_delta=0.02,
        wall_clock_s=100,
        wall_clock_max_s=14400,
        all_deferred=False,
        aborted=False,
    )
    assert s is not None
    assert s.reason == HaltReason.ITERATION_CAP


def test_halt_when_asymptote_detected() -> None:
    history = [0.40, 0.41, 0.42, 0.41, 0.42, 0.41]  # 직전 5개 변화 < 0.02
    s = compute_halt_signal(
        iteration=10,
        aggregate_history=history,
        iteration_cap=30,
        asymptote_window=5,
        asymptote_delta=0.02,
        wall_clock_s=100,
        wall_clock_max_s=14400,
        all_deferred=False,
        aborted=False,
    )
    assert s is not None
    assert s.reason == HaltReason.ASYMPTOTE


def test_halt_when_all_deferred() -> None:
    s = compute_halt_signal(
        iteration=5,
        aggregate_history=[],
        iteration_cap=30,
        asymptote_window=5,
        asymptote_delta=0.02,
        wall_clock_s=100,
        wall_clock_max_s=14400,
        all_deferred=True,
        aborted=False,
    )
    assert s is not None
    assert s.reason == HaltReason.ALL_DEFERRED


def test_halt_when_wall_clock_exceeded() -> None:
    s = compute_halt_signal(
        iteration=5,
        aggregate_history=[0.5],
        iteration_cap=30,
        asymptote_window=5,
        asymptote_delta=0.02,
        wall_clock_s=100_000,
        wall_clock_max_s=14400,
        all_deferred=False,
        aborted=False,
    )
    assert s is not None
    assert s.reason == HaltReason.WALL_CLOCK


def test_halt_when_aborted() -> None:
    s = compute_halt_signal(
        iteration=5,
        aggregate_history=[0.5],
        iteration_cap=30,
        asymptote_window=5,
        asymptote_delta=0.02,
        wall_clock_s=100,
        wall_clock_max_s=14400,
        all_deferred=False,
        aborted=True,
    )
    assert s is not None
    assert s.reason == HaltReason.USER_ABORT


def test_no_halt_when_progressing() -> None:
    s = compute_halt_signal(
        iteration=5,
        aggregate_history=[0.4, 0.5, 0.6],
        iteration_cap=30,
        asymptote_window=5,
        asymptote_delta=0.02,
        wall_clock_s=100,
        wall_clock_max_s=14400,
        all_deferred=False,
        aborted=False,
    )
    assert s is None
