"""mimiron gate <slug> artifacts — execute phase 종료 detection + phase 전이.

결함 #8 fix: scan이 phase_done=true일 때 phase=evaluate로 결정적 전이.
T02 (post-hoc drift): phase_done이어도 declared post_hash vs 디스크 상태가
어긋나면 drift task 수에 따라 verdict가 needs_review/fail로 떨어진다.
"""
import json
from pathlib import Path
import yaml
import pytest
from mimiron.cli import main
from mimiron.hash_util import sha256_file
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


# ---------------------------------------------------------------------------
# T02 — post-hoc drift verification helpers + tests
# ---------------------------------------------------------------------------


def _write_target_and_artifacts(
    tmp_project: Path,
    sidecar: Path,
    *,
    task_id: str,
    rel_path: str,
    content: str,
) -> Path:
    """task_id에 해당하는 declared file을 실제 디스크에 만들고
    sidecar/tasks/<task_id>/artifacts.json도 함께 기록한다.

    반환값은 작성된 target 파일 absolute path. 호출자가 이 파일 내용을
    *나중에* 바꾸면 post-hoc drift가 발생한다.
    """
    target = tmp_project / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    art_path = sidecar / "tasks" / task_id / "artifacts.json"
    art_path.parent.mkdir(parents=True, exist_ok=True)
    art_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "task_id": task_id,
                "declared_files": [
                    {
                        "path": rel_path,
                        "action": "create",
                        "pre_hash": None,
                        "post_hash": sha256_file(target),
                        "pre_mtime": None,
                        "post_mtime": "2026-05-24T00:00:00Z",
                    }
                ],
                "worker_summary": f"created {rel_path}",
            }
        )
    )
    return target


def test_one_task_drift_yields_needs_review(
    tmp_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC01 — 1개 task의 declared file이 post-hoc로 변형되면 needs_review."""
    sidecar = _seed_execute_with_plan(
        tmp_project, monkeypatch,
        tasks=[_task("T01"), _task("T02")],
        completed=["T01", "T02"],
    )
    # T01 declared file은 정상, T02 declared file을 commit 이후 외부 수정.
    _write_target_and_artifacts(
        tmp_project, sidecar, task_id="T01", rel_path="T01.py",
        content="print('T01')\n",
    )
    t02_target = _write_target_and_artifacts(
        tmp_project, sidecar, task_id="T02", rel_path="T02.py",
        content="print('T02 original')\n",
    )
    # post-hoc tampering: hash가 바뀌도록 내용 수정.
    t02_target.write_text("print('T02 tampered')\n")

    rc = main(["gate", "demo", "artifacts"])
    # needs_review는 hard fail 아님 — 호출 자체는 성공 코드여야 한다.
    assert rc == 0
    state = State.load(sidecar / "state.json")
    # needs_review라 evaluate로 전이되지 않고 execute에 머무름.
    assert state.phase == "execute"
    assert any(
        g.kind == "artifacts" and g.verdict == "needs_review"
        for g in state.gate_history
    )
    v = json.loads((sidecar / "evaluation" / "artifacts.json").read_text())
    assert v["verdict"] == "needs_review"
    assert len(v["details"]["drift"]) == 1
    assert v["details"]["drift"][0]["task_id"] == "T02"
    assert "T02.py" in v["details"]["drift"][0]["files"]


def test_two_task_drift_yields_fail(
    tmp_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC02 — 2개 이상 task drift → verdict=fail."""
    sidecar = _seed_execute_with_plan(
        tmp_project, monkeypatch,
        tasks=[_task("T01"), _task("T02")],
        completed=["T01", "T02"],
    )
    t01_target = _write_target_and_artifacts(
        tmp_project, sidecar, task_id="T01", rel_path="T01.py",
        content="print('T01 original')\n",
    )
    t02_target = _write_target_and_artifacts(
        tmp_project, sidecar, task_id="T02", rel_path="T02.py",
        content="print('T02 original')\n",
    )
    # 두 task 모두 post-hoc tampering.
    t01_target.write_text("print('T01 tampered')\n")
    t02_target.write_text("print('T02 tampered')\n")

    rc = main(["gate", "demo", "artifacts"])
    assert rc != 0  # fail은 비-zero exit
    state = State.load(sidecar / "state.json")
    # fail이라 phase는 execute 그대로.
    assert state.phase == "execute"
    assert any(
        g.kind == "artifacts" and g.verdict == "fail"
        for g in state.gate_history
    )
    v = json.loads((sidecar / "evaluation" / "artifacts.json").read_text())
    assert v["verdict"] == "fail"
    drifted_ids = {entry["task_id"] for entry in v["details"]["drift"]}
    assert drifted_ids == {"T01", "T02"}
    assert len(v["details"]["drift"]) >= 2


def test_drift_details_schema(
    tmp_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC04 — verdict.json.details["drift"]는 list[{task_id: str, files: list[str]}]."""
    sidecar = _seed_execute_with_plan(
        tmp_project, monkeypatch,
        tasks=[_task("T01")],
        completed=["T01"],
    )
    target = _write_target_and_artifacts(
        tmp_project, sidecar, task_id="T01", rel_path="T01.py",
        content="print('original')\n",
    )
    target.write_text("print('tampered')\n")

    main(["gate", "demo", "artifacts"])
    v = json.loads((sidecar / "evaluation" / "artifacts.json").read_text())

    # drift 키 존재 + list 타입.
    assert "drift" in v["details"]
    drift = v["details"]["drift"]
    assert isinstance(drift, list)
    assert len(drift) == 1

    entry = drift[0]
    # 정확히 두 키 — task_id, files.
    assert set(entry.keys()) == {"task_id", "files"}
    assert isinstance(entry["task_id"], str)
    assert entry["task_id"] == "T01"
    assert isinstance(entry["files"], list)
    assert len(entry["files"]) >= 1
    assert all(isinstance(p, str) for p in entry["files"])
    assert "T01.py" in entry["files"]
