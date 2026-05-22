"""Outer-loop 메타 안전핀."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class HaltReason(str, Enum):
    ITERATION_CAP = "iteration_cap"
    ASYMPTOTE = "asymptote"
    ALL_DEFERRED = "all_deferred"
    WALL_CLOCK = "wall_clock"
    USER_ABORT = "user_abort"


@dataclass
class HaltSignal:
    reason: HaltReason
    detail: str


def compute_halt_signal(
    *,
    iteration: int,
    aggregate_history: list[float],
    iteration_cap: int,
    asymptote_window: int,
    asymptote_delta: float,
    wall_clock_s: float,
    wall_clock_max_s: float,
    all_deferred: bool,
    aborted: bool,
) -> HaltSignal | None:
    if aborted:
        return HaltSignal(HaltReason.USER_ABORT, "abort requested")
    if iteration >= iteration_cap:
        return HaltSignal(HaltReason.ITERATION_CAP, f"reached {iteration_cap}")
    if wall_clock_s >= wall_clock_max_s:
        return HaltSignal(
            HaltReason.WALL_CLOCK,
            f"{wall_clock_s:.0f}s >= {wall_clock_max_s:.0f}s",
        )
    if all_deferred:
        return HaltSignal(HaltReason.ALL_DEFERRED, "all benchmarks deferred")
    if len(aggregate_history) >= asymptote_window + 1:
        window = aggregate_history[-(asymptote_window + 1):]
        deltas = [abs(window[i + 1] - window[i]) for i in range(asymptote_window)]
        if all(d < asymptote_delta for d in deltas):
            return HaltSignal(
                HaltReason.ASYMPTOTE,
                f"|Δ| < {asymptote_delta} for last {asymptote_window} iterations",
            )
    return None
