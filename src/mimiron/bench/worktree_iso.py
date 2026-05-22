"""git worktree로 bench 격리. 사용자 작업 트리를 절대 건드리지 않는다."""
from __future__ import annotations

import contextlib
import shutil
import subprocess
from pathlib import Path
from typing import Iterator


class IsolationError(RuntimeError):
    pass


def _run(cmd: list[str], cwd: Path) -> None:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise IsolationError(
            f"git command failed: {' '.join(cmd)}\nstderr: {proc.stderr}"
        )


@contextlib.contextmanager
def isolate_at_ref(*, repo: Path, ref: str, dest: Path) -> Iterator[Path]:
    """`repo`를 `ref` 시점으로 *읽기 격리*. 원본은 건드리지 않는다.

    Yields:
        worktree 경로 (자동 정리됨)
    """
    if dest.exists():
        raise IsolationError(f"dest already exists: {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    _run(["git", "worktree", "add", "--detach", str(dest), ref], cwd=repo)
    try:
        yield dest
    finally:
        try:
            _run(["git", "worktree", "remove", "--force", str(dest)], cwd=repo)
        except IsolationError:
            pass
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
