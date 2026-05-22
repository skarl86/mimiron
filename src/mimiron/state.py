"""state.json — CLI가 단독 소유하는 결정적 장부."""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mimiron import SCHEMA_VERSION

VALID_PHASES = frozenset(
    {"clarify", "spec", "plan", "execute", "evaluate", "finalize", "done", "stuck", "paused"}
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class GateRecord:
    phase: str
    kind: str
    verdict: str  # "pass" | "fail" | "needs_review"
    score: float | None
    samples: list[float]
    ts: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "GateRecord":
        return cls(
            phase=d["phase"],
            kind=d["kind"],
            verdict=d["verdict"],
            score=d.get("score"),
            samples=list(d.get("samples", [])),
            ts=d["ts"],
        )


@dataclass
class State:
    schema_version: int
    slug: str
    phase: str
    persistent: bool
    paused: bool
    spec_hash: str | None
    spec_unlocked: bool
    current_task: str | None
    completed_task_ids: list[str]
    in_flight_task_ids: list[str]
    retries: dict[str, int]
    gate_history: list[GateRecord]
    consecutive_gate_fails: int
    wall_clock_started_at: str
    token_usage: int
    created_at: str
    updated_at: str

    @classmethod
    def create(cls, slug: str, persistent: bool = True) -> "State":
        now = _now_iso()
        return cls(
            schema_version=SCHEMA_VERSION,
            slug=slug,
            phase="clarify",
            persistent=persistent,
            paused=False,
            spec_hash=None,
            spec_unlocked=False,
            current_task=None,
            completed_task_ids=[],
            in_flight_task_ids=[],
            retries={},
            gate_history=[],
            consecutive_gate_fails=0,
            wall_clock_started_at=now,
            token_usage=0,
            created_at=now,
            updated_at=now,
        )

    @classmethod
    def load(cls, path: Path) -> "State":
        raw = json.loads(path.read_text(encoding="utf-8"))
        sv = raw.get("schema_version")
        if sv != SCHEMA_VERSION:
            raise ValueError(
                f"schema_version mismatch: file={sv} expected={SCHEMA_VERSION}. "
                "Run mimiron migrate or upgrade CLI."
            )
        phase = raw.get("phase")
        if phase not in VALID_PHASES:
            raise ValueError(f"invalid phase {phase!r}; expected one of {sorted(VALID_PHASES)}")
        raw["gate_history"] = [GateRecord.from_dict(g) for g in raw.get("gate_history", [])]
        return cls(**raw)

    def save(self, path: Path) -> None:
        self.updated_at = _now_iso()
        path.parent.mkdir(parents=True, exist_ok=True)
        d = asdict(self)
        d["gate_history"] = [g.to_dict() for g in self.gate_history]
        path.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
