"""mimiron gate <slug> plan_integrity — plan.yaml validate + phase 전이.

결함 #6 fix: plan → execute phase transition을 결정적으로 박는 게이트.
"""
import json
from pathlib import Path
import yaml
import pytest
from mimiron.cli import main
from mimiron.state import State


def _seed_plan_phase(tmp_project: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """init + state.phase=plan + state.spec_hash=<hash> 직접 박기."""
    monkeypatch.chdir(tmp_project)
    main(["init", "demo"])
    sidecar = tmp_project / ".mimiron" / "demo"
    # spec.yaml 작성 후 hash 계산
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
    state = State.load(sidecar / "state.json")
    state.phase = "plan"
    state.spec_hash = spec_hash
    state.save(sidecar / "state.json")
    return sidecar


def _write_plan(sidecar: Path, *, spec_hash: str, tasks: list[dict]) -> None:
    (sidecar / "plan.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": 1, "slug": "demo",
                "spec_hash": spec_hash,
                "tasks": tasks,
            }
        )
    )


def _default_tasks() -> list[dict]:
    return [
        {
            "id": "T01", "title": "x", "worker": "worker",
            "depends_on": [], "owned_files": ["a.py"],
            "expected_artifacts": ["a.py"], "timeout_s": 600,
        }
    ]


def test_plan_integrity_missing_plan_yaml_runtime_error(
    tmp_project: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed_plan_phase(tmp_project, monkeypatch)
    rc = main(["gate", "demo", "plan_integrity"])
    assert rc != 0
    err = capsys.readouterr().err
    assert "plan.yaml" in err


def test_plan_integrity_pass_transitions_to_execute(
    tmp_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sidecar = _seed_plan_phase(tmp_project, monkeypatch)
    state = State.load(sidecar / "state.json")
    _write_plan(sidecar, spec_hash=state.spec_hash, tasks=_default_tasks())
    rc = main(["gate", "demo", "plan_integrity"])
    assert rc == 0
    after = State.load(sidecar / "state.json")
    assert after.phase == "execute"
    assert any(g.kind == "plan_integrity" and g.verdict == "pass" for g in after.gate_history)


def test_plan_integrity_spec_hash_mismatch_fails(
    tmp_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sidecar = _seed_plan_phase(tmp_project, monkeypatch)
    _write_plan(sidecar, spec_hash="deadbeef" * 8, tasks=_default_tasks())
    rc = main(["gate", "demo", "plan_integrity"])
    assert rc != 0
    after = State.load(sidecar / "state.json")
    assert after.phase != "execute"


def test_plan_integrity_cycle_in_dag_fails(
    tmp_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sidecar = _seed_plan_phase(tmp_project, monkeypatch)
    state = State.load(sidecar / "state.json")
    _write_plan(
        sidecar, spec_hash=state.spec_hash,
        tasks=[
            {"id": "T01", "title": "x", "worker": "worker", "depends_on": ["T02"],
             "owned_files": ["a.py"], "expected_artifacts": ["a.py"], "timeout_s": 600},
            {"id": "T02", "title": "y", "worker": "worker", "depends_on": ["T01"],
             "owned_files": ["b.py"], "expected_artifacts": ["b.py"], "timeout_s": 600},
        ],
    )
    rc = main(["gate", "demo", "plan_integrity"])
    assert rc != 0
    after = State.load(sidecar / "state.json")
    assert after.phase != "execute"


def test_plan_integrity_ownership_conflict_fails(
    tmp_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sidecar = _seed_plan_phase(tmp_project, monkeypatch)
    state = State.load(sidecar / "state.json")
    _write_plan(
        sidecar, spec_hash=state.spec_hash,
        tasks=[
            {"id": "T01", "title": "x", "worker": "worker", "depends_on": [],
             "owned_files": ["a.py"], "expected_artifacts": ["a.py"], "timeout_s": 600},
            {"id": "T02", "title": "y", "worker": "worker", "depends_on": [],
             "owned_files": ["a.py"], "expected_artifacts": ["a.py"], "timeout_s": 600},
        ],
    )
    rc = main(["gate", "demo", "plan_integrity"])
    assert rc != 0


def test_plan_integrity_writes_verdict_json(
    tmp_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sidecar = _seed_plan_phase(tmp_project, monkeypatch)
    state = State.load(sidecar / "state.json")
    _write_plan(sidecar, spec_hash=state.spec_hash, tasks=_default_tasks())
    main(["gate", "demo", "plan_integrity"])
    verdict_path = sidecar / "evaluation" / "plan_integrity.json"
    assert verdict_path.exists()
    v = json.loads(verdict_path.read_text())
    assert v["kind"] == "plan_integrity"
    assert v["verdict"] == "pass"


# ---------------------------------------------------------------------------
# plan_smells coverage (AC02–AC05, AC08)
# ---------------------------------------------------------------------------


def _task(
    tid: str,
    *,
    files: list[str],
    depends_on: list[str] | None = None,
    worker: str = "worker",
) -> dict:
    return {
        "id": tid,
        "title": f"task {tid}",
        "worker": worker,
        "depends_on": list(depends_on or []),
        "owned_files": files,
        "expected_artifacts": files,
        "timeout_s": 600,
    }


def _read_verdict(sidecar: Path) -> dict:
    return json.loads(
        (sidecar / "evaluation" / "plan_integrity.json").read_text()
    )


def test_no_smells_yields_pass(
    tmp_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC02: 작은 plan (2 tasks, 1 file each, no reviewer) → verdict=pass.

    details 에 metrics 는 있고 smells 키는 없어야 한다.
    """
    sidecar = _seed_plan_phase(tmp_project, monkeypatch)
    state = State.load(sidecar / "state.json")
    _write_plan(
        sidecar,
        spec_hash=state.spec_hash,
        tasks=[
            _task("T01", files=["src/a.py"]),
            _task("T02", files=["src/b.py"], depends_on=["T01"]),
        ],
    )
    rc = main(["gate", "demo", "plan_integrity"])
    assert rc == 0
    v = _read_verdict(sidecar)
    assert v["verdict"] == "pass"
    assert "metrics" in v["details"]
    assert "smells" not in v["details"]


def test_one_smell_yields_pass_with_details(
    tmp_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC03: 정확히 한 smell 만 발생 → verdict=pass + smells 길이 1.

    한 task 에 owned_files 6개 → avg=6>5 → avg_files_per_task smell 만 발생.
    dag_depth=1, reviewer_ratio=0 은 임계 이하.
    """
    sidecar = _seed_plan_phase(tmp_project, monkeypatch)
    state = State.load(sidecar / "state.json")
    files = [f"src/heavy_{i}.py" for i in range(6)]
    _write_plan(
        sidecar,
        spec_hash=state.spec_hash,
        tasks=[_task("T01", files=files)],
    )
    rc = main(["gate", "demo", "plan_integrity"])
    assert rc == 0
    v = _read_verdict(sidecar)
    assert v["verdict"] == "pass"
    assert "smells" in v["details"]
    assert len(v["details"]["smells"]) == 1
    smell = v["details"]["smells"][0]
    assert smell["name"] == "avg_files_per_task"
    assert "value" in smell
    assert "threshold" in smell


def test_two_or_more_smells_yields_needs_review(
    tmp_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC04: 두 개 이상의 smell → verdict=needs_review.

    6-task linear chain, 각 task 가 6개의 unique owned_files →
    avg_files_per_task=6>5, dag_depth=6>5 → 2개의 smell 발생.
    """
    sidecar = _seed_plan_phase(tmp_project, monkeypatch)
    state = State.load(sidecar / "state.json")
    tasks = []
    for i in range(1, 7):
        tid = f"T0{i}"
        deps = [f"T0{i - 1}"] if i > 1 else []
        files = [f"src/file_{i}_{j}.py" for j in range(6)]
        tasks.append(_task(tid, files=files, depends_on=deps))
    _write_plan(sidecar, spec_hash=state.spec_hash, tasks=tasks)
    rc = main(["gate", "demo", "plan_integrity"])
    # needs_review 는 fail 이 아니므로 exit code 는 0.
    assert rc == 0
    v = _read_verdict(sidecar)
    assert v["verdict"] == "needs_review"
    assert "smells" in v["details"]
    assert len(v["details"]["smells"]) >= 2
    names = {s["name"] for s in v["details"]["smells"]}
    assert "avg_files_per_task" in names
    assert "dag_depth" in names


def test_details_schema(
    tmp_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC05: details 는 항상 task_count + metrics(세 sub-key) 를 가진다."""
    sidecar = _seed_plan_phase(tmp_project, monkeypatch)
    state = State.load(sidecar / "state.json")
    _write_plan(sidecar, spec_hash=state.spec_hash, tasks=_default_tasks())
    main(["gate", "demo", "plan_integrity"])
    v = _read_verdict(sidecar)
    details = v["details"]
    assert isinstance(details["task_count"], int)
    metrics = details["metrics"]
    assert isinstance(metrics, dict)
    assert isinstance(metrics["avg_files_per_task"], (int, float))
    assert isinstance(metrics["dag_depth"], int)
    assert isinstance(metrics["reviewer_ratio"], (int, float))


def test_needs_review_does_not_pause(
    tmp_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC08: plan_integrity needs_review 는 state.paused 를 토글하지 않는다.

    AC04 와 동일한 plan 으로 needs_review 를 만든 뒤 state.paused 가 False
    인지 확인.
    """
    sidecar = _seed_plan_phase(tmp_project, monkeypatch)
    state = State.load(sidecar / "state.json")
    tasks = []
    for i in range(1, 7):
        tid = f"T0{i}"
        deps = [f"T0{i - 1}"] if i > 1 else []
        files = [f"src/file_{i}_{j}.py" for j in range(6)]
        tasks.append(_task(tid, files=files, depends_on=deps))
    _write_plan(sidecar, spec_hash=state.spec_hash, tasks=tasks)
    rc = main(["gate", "demo", "plan_integrity"])
    assert rc == 0
    v = _read_verdict(sidecar)
    assert v["verdict"] == "needs_review"
    after = State.load(sidecar / "state.json")
    assert after.paused is False
