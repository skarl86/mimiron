"""DAG scanner — 다음 ready task를 결정적으로 결정."""
from __future__ import annotations

from dataclasses import dataclass
from mimiron.plan import Plan


@dataclass
class ScanResult:
    ready: list[str]
    in_flight: list[str]
    pending: list[str]
    phase_done: bool


def scan(plan: Plan, completed_ids: list[str], in_flight_ids: list[str]) -> ScanResult:
    completed = set(completed_ids)
    in_flight = set(in_flight_ids)
    by_id = {t.id: t for t in plan.tasks}

    in_flight_files: set[str] = set()
    for tid in in_flight:
        in_flight_files.update(by_id[tid].owned_files)

    ready: list[str] = []
    pending: list[str] = []
    for t in plan.tasks:
        if t.id in completed or t.id in in_flight:
            continue
        deps_ok = all(dep in completed for dep in t.depends_on)
        if not deps_ok:
            pending.append(t.id)
            continue
        # 파일 소유권 충돌 (in-flight와)
        if any(f in in_flight_files for f in t.owned_files):
            pending.append(t.id)
            continue
        ready.append(t.id)

    phase_done = (
        not ready
        and not in_flight
        and not pending
        and all(t.id in completed for t in plan.tasks)
    )
    return ScanResult(
        ready=sorted(ready),
        in_flight=sorted(in_flight),
        pending=sorted(pending),
        phase_done=phase_done,
    )
