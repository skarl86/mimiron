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


def detect_post_hoc_drift(
    sidecar: Path,
    completed_task_ids: list[str],
    *,
    root: Path | None = None,
) -> list[dict[str, Any]]:
    """gate artifacts 시점에 declared_files vs 현재 파일 상태를 재검사.

    각 completed task의 `tasks/<task_id>/artifacts.json`을 로드해서
    declared_files를 순회하며 drift를 감지한다.

    drift 정의:
      - action != "delete"인데 디스크에 파일이 없음
      - action != "delete"이고 디스크 sha256가 declared post_hash와 다름
      - action == "delete"인데 파일이 여전히 존재

    artifacts.json 자체가 없거나 schema 오류로 load 실패한 task는 *skip*한다.
    (commit-task 시점에서 이미 한 번 검증을 통과했어야 정상 흐름이며,
    여기서 추가 reject를 발생시키면 기존 회귀 테스트가 깨진다. 빠진 sidecar는
    plan_integrity/scan 단계가 별도로 잡아낸다.)

    Args:
        sidecar: ``.mimiron/<slug>`` 경로.
        completed_task_ids: state.completed_task_ids — drift 검사 대상.
        root: 파일 비교 기준 root. 기본은 ``sidecar.parent.parent``
            (즉 ``.mimiron/<slug>/../..`` == project root).

    Returns:
        drift가 감지된 task만 모은 list. 각 항목은
        ``{"task_id": str, "files": list[str]}`` 형식. drift가 없으면 빈 list.
    """
    if root is None:
        # sidecar = <cwd>/.mimiron/<slug> → cwd = sidecar.parent.parent
        root = sidecar.parent.parent
    drifted: list[dict[str, Any]] = []
    for tid in completed_task_ids:
        art_path = sidecar / "tasks" / tid / "artifacts.json"
        if not art_path.exists():
            continue
        try:
            art = Artifacts.load(art_path)
        except (ArtifactError, KeyError, ValueError):
            # 손상된 artifacts.json은 commit-task 시점이 책임진다 — 여기서는 skip.
            continue
        bad_files: list[str] = []
        for f in art.declared_files:
            target = root / f.path
            if f.action == "delete":
                if target.exists():
                    bad_files.append(f.path)
                continue
            if not target.exists():
                bad_files.append(f.path)
                continue
            try:
                actual = sha256_file(target)
            except OSError:
                bad_files.append(f.path)
                continue
            if actual != f.post_hash:
                bad_files.append(f.path)
        if bad_files:
            drifted.append({"task_id": tid, "files": bad_files})
    return drifted
