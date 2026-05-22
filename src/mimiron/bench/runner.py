"""bench runner — 단일 case 실행 + verdict 산출."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import yaml


class BenchmarkError(ValueError):
    """Benchmark fixture 오류."""


@dataclass
class Benchmark:
    id: str
    repo: str
    base_ref: str
    target_ref: str
    issue_text_file: str
    expected_diff_file: str
    test_command: str
    difficulty: str
    notes: str
    yaml_dir: Path  # benchmark.yaml의 디렉토리 (relative 경로 해석용)

    @classmethod
    def load(cls, path: Path) -> "Benchmark":
        raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        required = [
            "id", "repo", "base_ref", "target_ref",
            "issue_text_file", "expected_diff_file", "test_command",
        ]
        for k in required:
            if k not in raw:
                raise BenchmarkError(f"missing required field {k!r}")
        return cls(
            id=raw["id"],
            repo=raw["repo"],
            base_ref=raw["base_ref"],
            target_ref=raw["target_ref"],
            issue_text_file=raw["issue_text_file"],
            expected_diff_file=raw["expected_diff_file"],
            test_command=raw["test_command"],
            difficulty=raw.get("difficulty", "unknown"),
            notes=raw.get("notes", ""),
            yaml_dir=path.parent,
        )

    def issue_text(self) -> str:
        return (self.yaml_dir / self.issue_text_file).read_text(encoding="utf-8")

    def expected_diff(self) -> str:
        return (self.yaml_dir / self.expected_diff_file).read_text(encoding="utf-8")
