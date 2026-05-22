"""verdict.json — 게이트 판정 결과."""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mimiron import SCHEMA_VERSION

VALID_KINDS = frozenset(
    {"mechanical", "semantic", "ambiguity", "quality", "plan_integrity", "artifacts", "spec_freeze"}
)
VALID_VERDICTS = frozenset({"pass", "fail", "needs_review"})


@dataclass
class Verdict:
    schema_version: int
    slug: str
    phase: str
    kind: str
    verdict: str
    score: float | None
    samples: list[float]
    details: dict[str, Any]
    ts: str

    @classmethod
    def make(
        cls,
        *,
        slug: str,
        phase: str,
        kind: str,
        verdict: str,
        score: float | None = None,
        samples: list[float] | None = None,
        details: dict[str, Any] | None = None,
    ) -> "Verdict":
        if kind not in VALID_KINDS:
            raise ValueError(f"invalid kind {kind!r}")
        if verdict not in VALID_VERDICTS:
            raise ValueError(f"invalid verdict {verdict!r}")
        return cls(
            schema_version=SCHEMA_VERSION,
            slug=slug,
            phase=phase,
            kind=kind,
            verdict=verdict,
            score=score,
            samples=samples or [],
            details=details or {},
            ts=datetime.now(timezone.utc).isoformat(),
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
