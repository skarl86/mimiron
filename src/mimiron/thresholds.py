"""_global/thresholds.yaml 로더."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import yaml


@dataclass
class Thresholds:
    ambiguity_max: float
    spec_quality_min: float
    cutoff_case: float
    cutoff_global: float
    w_test: float
    w_sim: float
    wall_clock_max_s: int
    token_budget: int
    max_parallel_workers: int
    certainty_band: float

    @classmethod
    def defaults(cls) -> "Thresholds":
        return cls(
            ambiguity_max=0.2,
            spec_quality_min=0.85,
            cutoff_case=0.75,
            cutoff_global=0.75,
            w_test=0.6,
            w_sim=0.4,
            wall_clock_max_s=14400,
            token_budget=500_000,
            max_parallel_workers=4,
            certainty_band=0.05,
        )

    @classmethod
    def load_or_default(cls, path: Path) -> "Thresholds":
        if not path.exists():
            return cls.defaults()
        raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        d = cls.defaults().__dict__.copy()
        d.update(raw)
        return cls(**d)
