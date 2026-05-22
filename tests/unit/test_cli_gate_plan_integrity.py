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
