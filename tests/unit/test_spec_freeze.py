"""plan 진입 후 spec.yaml mutate 감지."""
import json
import yaml
from pathlib import Path
import pytest
from mimiron.cli import main


def _to_plan_phase(tmp_project: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_project)
    main(["init", "demo"])
    sidecar = tmp_project / ".mimiron" / "demo"
    (sidecar / "clarification.md").write_text(
        "---\nslug: demo\nambiguity_score: 0.10\nsamples: [0.08, 0.10, 0.12]\n---\n# c\n"
    )
    main(["gate", "demo", "ambiguity"])
    (sidecar / "spec.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": 1, "slug": "demo", "goal": "g",
                "constraints": [], "acceptance_criteria": [], "ontology": {},
                "hypothesis": [], "quality_score": 0.92, "ambiguity_score": 0.10,
            }
        )
    )
    (sidecar / "quality.samples.json").write_text("[0.90, 0.92, 0.94]")
    main(["gate", "demo", "quality"])
    return sidecar


def test_scan_fails_when_spec_hash_drifts(
    tmp_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sidecar = _to_plan_phase(tmp_project, monkeypatch)
    (sidecar / "plan.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": 1, "slug": "demo",
                "spec_hash": "deadbeef" * 8,  # 64-char wrong hash
                "tasks": [
                    {
                        "id": "T01", "title": "x", "worker": "worker",
                        "depends_on": [], "owned_files": ["a.py"],
                        "expected_artifacts": ["a.py"], "timeout_s": 600,
                    }
                ],
            }
        )
    )
    rc = main(["scan", "demo"])
    assert rc != 0


def test_scan_passes_when_spec_hash_matches(
    tmp_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sidecar = _to_plan_phase(tmp_project, monkeypatch)
    state = json.loads((sidecar / "state.json").read_text())
    (sidecar / "plan.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": 1, "slug": "demo",
                "spec_hash": state["spec_hash"],
                "tasks": [
                    {
                        "id": "T01", "title": "x", "worker": "worker",
                        "depends_on": [], "owned_files": ["a.py"],
                        "expected_artifacts": ["a.py"], "timeout_s": 600,
                    }
                ],
            }
        )
    )
    rc = main(["scan", "demo"])
    assert rc == 0


def _seed_commit_task_artifacts(sidecar: Path, tmp_project: Path) -> None:
    """commit-task용 artifacts.json + target 파일 준비."""
    from mimiron.hash_util import sha256_file
    target = tmp_project / "a.py"
    target.write_text("print('a')\n")
    art = sidecar / "tasks" / "T01" / "artifacts.json"
    art.parent.mkdir(parents=True)
    art.write_text(
        json.dumps(
            {
                "schema_version": 1, "task_id": "T01",
                "declared_files": [
                    {
                        "path": "a.py", "action": "create",
                        "pre_hash": None, "post_hash": sha256_file(target),
                        "pre_mtime": None, "post_mtime": "2026-05-22T00:00:00Z",
                    }
                ],
                "worker_summary": "created a.py",
            }
        )
    )


def test_commit_task_blocks_when_spec_hash_drifts(
    tmp_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sidecar = _to_plan_phase(tmp_project, monkeypatch)
    # 사용자가 plan 진입 후 spec.yaml을 *불법적으로* 수정
    spec_path = sidecar / "spec.yaml"
    raw = yaml.safe_load(spec_path.read_text())
    raw["goal"] = "MUTATED — should make state.spec_hash mismatch"
    spec_path.write_text(yaml.safe_dump(raw))
    _seed_commit_task_artifacts(sidecar, tmp_project)
    rc = main(["commit-task", "demo", "T01"])
    assert rc != 0
    state = json.loads((sidecar / "state.json").read_text())
    assert state["phase"] == "stuck"


def test_commit_task_passes_when_spec_hash_matches(
    tmp_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sidecar = _to_plan_phase(tmp_project, monkeypatch)
    _seed_commit_task_artifacts(sidecar, tmp_project)
    rc = main(["commit-task", "demo", "T01"])
    assert rc == 0


def test_commit_task_allows_when_spec_unlocked(
    tmp_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """spec_unlocked=True (unstuck flow)이면 hash drift 허용."""
    sidecar = _to_plan_phase(tmp_project, monkeypatch)
    state_path = sidecar / "state.json"
    state_raw = json.loads(state_path.read_text())
    state_raw["spec_unlocked"] = True
    state_path.write_text(json.dumps(state_raw))
    # spec mutate
    spec_path = sidecar / "spec.yaml"
    raw = yaml.safe_load(spec_path.read_text())
    raw["goal"] = "intentional rewrite during unstuck"
    spec_path.write_text(yaml.safe_dump(raw))
    _seed_commit_task_artifacts(sidecar, tmp_project)
    rc = main(["commit-task", "demo", "T01"])
    assert rc == 0
