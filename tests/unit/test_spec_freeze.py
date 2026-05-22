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
