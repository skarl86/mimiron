"""artifacts.json — 워커 산출 + 거짓 보고 방어."""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from mimiron import SCHEMA_VERSION
from mimiron.hash_util import sha256_file


class ArtifactError(ValueError):
    """Artifacts validation failure."""


VALID_ACTIONS = frozenset({"create", "modify", "delete"})


@dataclass
class DeclaredFile:
    path: str
    action: str  # create | modify | delete
    pre_hash: str | None
    post_hash: str
    pre_mtime: str | None
    post_mtime: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "DeclaredFile":
        action = d.get("action")
        if action not in VALID_ACTIONS:
            raise ArtifactError(f"invalid action {action!r}")
        return cls(
            path=d["path"],
            action=action,
            pre_hash=d.get("pre_hash"),
            post_hash=d["post_hash"],
            pre_mtime=d.get("pre_mtime"),
            post_mtime=d["post_mtime"],
        )


@dataclass
class Artifacts:
    schema_version: int
    task_id: str
    declared_files: list[DeclaredFile]
    worker_summary: str

    @classmethod
    def load(cls, path: Path) -> "Artifacts":
        raw = json.loads(path.read_text(encoding="utf-8"))
        sv = raw.get("schema_version")
        if sv != SCHEMA_VERSION:
            raise ArtifactError(f"schema_version mismatch: {sv}")
        return cls(
            schema_version=sv,
            task_id=raw["task_id"],
            declared_files=[DeclaredFile.from_dict(d) for d in raw.get("declared_files", [])],
            worker_summary=raw.get("worker_summary", ""),
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        d = {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "declared_files": [f.to_dict() for f in self.declared_files],
            "worker_summary": self.worker_summary,
        }
        path.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def verify(self, root: Path) -> None:
        """파일이 실제로 declared_files대로 존재하고 post_hash와 일치하는지 검사."""
        for f in self.declared_files:
            target = root / f.path
            if f.action == "delete":
                if target.exists():
                    raise ArtifactError(f"task declared delete but {f.path!r} still exists")
                continue
            if not target.exists():
                raise ArtifactError(f"declared file missing: {f.path!r}")
            actual = sha256_file(target)
            if actual != f.post_hash:
                raise ArtifactError(
                    f"hash mismatch for {f.path!r}: declared={f.post_hash}, actual={actual}"
                )
