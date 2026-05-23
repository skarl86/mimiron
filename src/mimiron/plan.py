"""plan.yaml — DAG of tasks with file ownership."""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any
import yaml

from mimiron import SCHEMA_VERSION

if TYPE_CHECKING:
    from mimiron.thresholds import Thresholds


class PlanError(ValueError):
    """Plan validation failure."""


VALID_WORKERS = frozenset({"worker", "tester", "reviewer"})


@dataclass
class Task:
    id: str
    title: str
    worker: str
    depends_on: list[str]
    owned_files: list[str]
    expected_artifacts: list[str]
    timeout_s: int

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Task":
        if "id" not in d:
            raise PlanError("task missing required field 'id'")
        if "title" not in d:
            raise PlanError(f"task {d['id']!r} missing required field 'title'")
        worker = d.get("worker", "worker")
        if worker not in VALID_WORKERS:
            raise PlanError(f"invalid worker {worker!r} in task {d.get('id')}")
        return cls(
            id=d["id"],
            title=d["title"],
            worker=worker,
            depends_on=list(d.get("depends_on", [])),
            owned_files=list(d.get("owned_files", [])),
            expected_artifacts=list(d.get("expected_artifacts", [])),
            timeout_s=int(d.get("timeout_s", 600)),
        )


@dataclass
class Plan:
    schema_version: int
    slug: str
    spec_hash: str
    tasks: list[Task]

    @classmethod
    def load(cls, path: Path) -> "Plan":
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if raw is None:
            raise PlanError("plan.yaml is empty")
        if not isinstance(raw, dict):
            raise PlanError(f"plan.yaml root must be a mapping, got {type(raw).__name__}")
        sv = raw.get("schema_version")
        if sv != SCHEMA_VERSION:
            raise PlanError(f"schema_version mismatch: {sv} != {SCHEMA_VERSION}")
        for field in ("slug", "spec_hash", "tasks"):
            if field not in raw:
                raise PlanError(f"plan.yaml missing required field {field!r}")
        return cls(
            schema_version=sv,
            slug=raw["slug"],
            spec_hash=raw["spec_hash"],
            tasks=[Task.from_dict(t) for t in raw["tasks"]],
        )

    def validate(self) -> None:
        ids = [t.id for t in self.tasks]
        if len(ids) != len(set(ids)):
            raise PlanError("duplicate task ids")
        ids_set = set(ids)
        for t in self.tasks:
            for dep in t.depends_on:
                if dep not in ids_set:
                    raise PlanError(f"task {t.id}: unknown depends_on {dep!r}")
        self._detect_cycles()
        self._detect_ownership_conflicts()

    def _detect_cycles(self) -> None:
        by_id = {t.id: t for t in self.tasks}
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {tid: WHITE for tid in by_id}

        def dfs(tid: str) -> None:
            color[tid] = GRAY
            for dep in by_id[tid].depends_on:
                if color[dep] == GRAY:
                    raise PlanError(f"cycle detected involving {tid} → {dep}")
                if color[dep] == WHITE:
                    dfs(dep)
            color[tid] = BLACK

        for tid in by_id:
            if color[tid] == WHITE:
                dfs(tid)

    def _detect_ownership_conflicts(self) -> None:
        owners: dict[str, str] = {}
        for t in self.tasks:
            for f in t.owned_files:
                if f in owners:
                    raise PlanError(
                        f"owned_files conflict: {f!r} claimed by both "
                        f"{owners[f]} and {t.id}"
                    )
                owners[f] = t.id


def detect_plan_smells(
    plan: Plan,
    thresholds: Thresholds,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Compute structural quality smells from a Plan.

    Pure function. No I/O. Does not mutate ``plan``.

    Returns a ``(metrics, smells)`` tuple. ``metrics`` is always populated
    with ``avg_files_per_task`` (float), ``dag_depth`` (int), and
    ``reviewer_ratio`` (float). ``smells`` lists every smell whose metric
    is **strictly greater than** its threshold (boundary values do not fire).
    """
    tasks = plan.tasks
    n = len(tasks)

    if n == 0:
        metrics: dict[str, Any] = {
            "avg_files_per_task": 0.0,
            "dag_depth": 0,
            "reviewer_ratio": 0.0,
        }
        return metrics, []

    avg_files_per_task = float(
        statistics.mean(len(t.owned_files) for t in tasks)
    )
    reviewer_ratio = sum(1 for t in tasks if t.worker == "reviewer") / n

    by_id = {t.id: t for t in tasks}
    depth_cache: dict[str, int] = {}

    def depth(tid: str) -> int:
        cached = depth_cache.get(tid)
        if cached is not None:
            return cached
        deps = by_id[tid].depends_on
        if not deps:
            d = 1
        else:
            d = 1 + max(depth(dep) for dep in deps if dep in by_id)
        depth_cache[tid] = d
        return d

    dag_depth = max(depth(t.id) for t in tasks)

    metrics = {
        "avg_files_per_task": avg_files_per_task,
        "dag_depth": dag_depth,
        "reviewer_ratio": reviewer_ratio,
    }

    smells: list[dict[str, Any]] = []
    if avg_files_per_task > thresholds.plan_smells_max_avg_files_per_task:
        smells.append({
            "name": "avg_files_per_task",
            "value": avg_files_per_task,
            "threshold": thresholds.plan_smells_max_avg_files_per_task,
        })
    if dag_depth > thresholds.plan_smells_max_dag_depth:
        smells.append({
            "name": "dag_depth",
            "value": dag_depth,
            "threshold": thresholds.plan_smells_max_dag_depth,
        })
    if reviewer_ratio > thresholds.plan_smells_max_reviewer_ratio:
        smells.append({
            "name": "reviewer_ratio",
            "value": reviewer_ratio,
            "threshold": thresholds.plan_smells_max_reviewer_ratio,
        })

    return metrics, smells
