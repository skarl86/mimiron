"""mimiron commit-task <slug> <task_id>."""
import json
import shutil
from pathlib import Path
import pytest
from mimiron.cli import main
from mimiron.hash_util import sha256_file


def test_commit_task_accepts_real_artifacts(
    tmp_project: Path,
    monkeypatch: pytest.MonkeyPatch,
    fixtures_dir: Path,
) -> None:
    monkeypatch.chdir(tmp_project)
    main(["init", "demo"])
    sidecar = tmp_project / ".mimiron" / "demo"
    shutil.copy(fixtures_dir / "plans" / "diamond.yaml", sidecar / "plan.yaml")
    target = tmp_project / "root.py"
    target.write_text("print('root')\n")
    art = sidecar / "tasks" / "T01" / "artifacts.json"
    art.parent.mkdir(parents=True)
    art.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "task_id": "T01",
                "declared_files": [
                    {
                        "path": "root.py",
                        "action": "create",
                        "pre_hash": None,
                        "post_hash": sha256_file(target),
                        "pre_mtime": None,
                        "post_mtime": "2026-05-22T00:00:00Z",
                    }
                ],
                "worker_summary": "created root.py",
            }
        )
    )
    rc = main(["commit-task", "demo", "T01"])
    assert rc == 0
    state = json.loads((sidecar / "state.json").read_text())
    assert "T01" in state["completed_task_ids"]


def test_commit_task_rejects_when_hash_mismatch(
    tmp_project: Path,
    monkeypatch: pytest.MonkeyPatch,
    fixtures_dir: Path,
) -> None:
    monkeypatch.chdir(tmp_project)
    main(["init", "demo"])
    sidecar = tmp_project / ".mimiron" / "demo"
    shutil.copy(fixtures_dir / "plans" / "diamond.yaml", sidecar / "plan.yaml")
    art = sidecar / "tasks" / "T01" / "artifacts.json"
    art.parent.mkdir(parents=True)
    art.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "task_id": "T01",
                "declared_files": [
                    {
                        "path": "root.py",
                        "action": "create",
                        "pre_hash": None,
                        "post_hash": "deadbeef",
                        "pre_mtime": None,
                        "post_mtime": "2026-05-22T00:00:00Z",
                    }
                ],
                "worker_summary": "lying",
            }
        )
    )
    rc = main(["commit-task", "demo", "T01"])
    assert rc != 0
    # retry counter incremented
    state = json.loads((sidecar / "state.json").read_text())
    assert state["retries"].get("T01", 0) >= 1
