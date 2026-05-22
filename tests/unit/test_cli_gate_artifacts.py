"""mimiron gate <slug> artifacts — execute phase 종료 detection + phase 전이.

결함 #8 fix: scan이 phase_done=true일 때 phase=evaluate로 결정적 전이.
"""
import json
from pathlib import Path
import yaml
import pytest
from mimiron.cli import main
from mimiron.state import State


def _seed_execute_with_plan(
    tmp_project: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    tasks: list[dict],
    completed: list[str] | None = None,
) -> Path:
    monkeypatch.chdir(tmp_project)
    main(["init", "demo"])
    sidecar = tmp_project / ".mimiron" / "demo"
    spec_path = sidecar / "spec.yaml"
    spec_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1, "slug": "demo", "goal": "g",
                "constraints": [], "acceptance_criteria": [],
                "ontology": {}, "hypothesis": [],
                "quality_score": 0.92, "ambiguity_score": 0.10,
            }
        )
    )
    from mimiron.spec import Spec
    spec_hash = Spec.compute_hash(spec_path)
    (sidecar / "plan.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": 1, "slug": "demo",
                "spec_hash": spec_hash, "tasks": tasks,
            }
        )
    )
    state = State.load(sidecar / "state.json")
    state.phase = "execute"
    state.spec_hash = spec_hash
    state.completed_task_ids = list(completed or [])
    state.save(sidecar / "state.json")
    return sidecar


def _task(tid: str, **kw) -> dict:
    base = {
        "id": tid, "title": "x", "worker": "worker",
        "depends_on": [], "owned_files": [f"{tid}.py"],
        "expected_artifacts": [f"{tid}.py"], "timeout_s": 600,
    }
    base.update(kw)
    return base


def test_artifacts_pass_when_phase_done_transitions_to_evaluate(
    tmp_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sidecar = _seed_execute_with_plan(
        tmp_project, monkeypatch,
        tasks=[_task("T01"), _task("T02")],
        completed=["T01", "T02"],
    )
    rc = main(["gate", "demo", "artifacts"])
    assert rc == 0
    state = State.load(sidecar / "state.json")
    assert state.phase == "evaluate"
    assert any(g.kind == "artifacts" and g.verdict == "pass" for g in state.gate_history)


def test_artifacts_fail_when_tasks_remain(
    tmp_project: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sidecar = _seed_execute_with_plan(
        tmp_project, monkeypatch,
        tasks=[_task("T01"), _task("T02")],
        completed=["T01"],  # T02 미완
    )
    rc = main(["gate", "demo", "artifacts"])
    assert rc != 0
    state = State.load(sidecar / "state.json")
    assert state.phase == "execute"  # 머무름


def test_artifacts_writes_verdict_json_with_pending(
    tmp_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sidecar = _seed_execute_with_plan(
        tmp_project, monkeypatch,
        tasks=[_task("T01"), _task("T02")],
        completed=["T01"],
    )
    main(["gate", "demo", "artifacts"])
    verdict_path = sidecar / "evaluation" / "artifacts.json"
    assert verdict_path.exists()
    v = json.loads(verdict_path.read_text())
    assert v["kind"] == "artifacts"
    assert v["verdict"] == "fail"
    # pending 정보가 details에 들어가야 함 (다음 행동 판단용)
    assert "pending" in v["details"] or "ready" in v["details"]


def test_artifacts_missing_plan_yaml_runtime_error(
    tmp_project: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_project)
    main(["init", "demo"])
    sidecar = tmp_project / ".mimiron" / "demo"
    state = State.load(sidecar / "state.json")
    state.phase = "execute"
    state.save(sidecar / "state.json")
    rc = main(["gate", "demo", "artifacts"])
    assert rc != 0
    err = capsys.readouterr().err
    assert "plan.yaml" in err
