"""게이트 pass 시 phase 자동 전이."""
import json
import yaml
from pathlib import Path
import pytest
from mimiron.cli import main


def _seed_clarify(tmp_project: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_project)
    main(["init", "demo"])
    sidecar = tmp_project / ".mimiron" / "demo"
    (sidecar / "clarification.md").write_text(
        "---\nslug: demo\nambiguity_score: 0.10\nsamples: [0.08, 0.10, 0.12]\n---\n# c\n"
    )
    return sidecar


def test_ambiguity_pass_transitions_clarify_to_spec(
    tmp_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sidecar = _seed_clarify(tmp_project, monkeypatch)
    main(["gate", "demo", "ambiguity"])
    state = json.loads((sidecar / "state.json").read_text())
    assert state["phase"] == "spec"


def test_quality_pass_transitions_spec_to_plan_and_writes_spec_hash(
    tmp_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sidecar = _seed_clarify(tmp_project, monkeypatch)
    main(["gate", "demo", "ambiguity"])
    (sidecar / "spec.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": 1, "slug": "demo", "goal": "g",
                "constraints": [], "acceptance_criteria": [], "ontology": {},
                "hypothesis": [],
                "quality_score": 0.92, "ambiguity_score": 0.10,
            }
        )
    )
    (sidecar / "quality.samples.json").write_text("[0.90, 0.92, 0.94]")
    main(["gate", "demo", "quality"])
    state = json.loads((sidecar / "state.json").read_text())
    assert state["phase"] == "plan"
    assert state["spec_hash"] is not None
    assert len(state["spec_hash"]) == 64
