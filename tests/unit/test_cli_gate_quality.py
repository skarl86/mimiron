"""quality gate."""
import json
from pathlib import Path
import pytest
import yaml
from mimiron.cli import main


def _setup_spec(
    tmp_project: Path, monkeypatch: pytest.MonkeyPatch, **kwargs
) -> Path:
    monkeypatch.chdir(tmp_project)
    main(["init", "demo"])
    sidecar = tmp_project / ".mimiron" / "demo"
    spec_dict = {
        "schema_version": 1,
        "slug": "demo",
        "goal": "g",
        "constraints": [],
        "acceptance_criteria": kwargs.get("acceptance_criteria", []),
        "ontology": {},
        "hypothesis": [],
        "quality_score": kwargs.get("quality_score", 0.92),
        "ambiguity_score": 0.10,
    }
    (sidecar / "spec.yaml").write_text(
        yaml.safe_dump(spec_dict, sort_keys=False, allow_unicode=True)
    )
    (sidecar / "quality.samples.json").write_text(
        json.dumps(kwargs.get("samples", [0.90, 0.92, 0.94]))
    )
    return sidecar


def test_quality_gate_passes(
    tmp_project: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _setup_spec(tmp_project, monkeypatch)
    capsys.readouterr()
    rc = main(["gate", "demo", "quality"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["verdict"] == "pass"


def test_quality_gate_penalty_when_reviewer_ratio_exceeds_half(
    tmp_project: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    acs = [
        {"id": f"AC0{i}", "desc": "d", "verify": {"kind": "reviewer"}}
        for i in range(3)
    ] + [
        {"id": "AC04", "desc": "d", "verify": {"kind": "test", "command": "true"}}
    ]
    # 3/4 = 0.75 > 0.5 → penalty 0.1 → 0.88 - 0.1 = 0.78 < 0.85, fail
    _setup_spec(
        tmp_project,
        monkeypatch,
        acceptance_criteria=acs,
        quality_score=0.88,
        samples=[0.86, 0.88, 0.90],
    )
    capsys.readouterr()
    rc = main(["gate", "demo", "quality"])
    out = json.loads(capsys.readouterr().out)
    assert out["verdict"] == "fail"
    assert rc != 0


def test_quality_gate_certainty_band(
    tmp_project: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _setup_spec(
        tmp_project,
        monkeypatch,
        quality_score=0.87,
        samples=[0.85, 0.87, 0.89],
    )
    capsys.readouterr()
    main(["gate", "demo", "quality"])
    out = json.loads(capsys.readouterr().out)
    # 0.87 in band [0.80, 0.90] → needs_review
    assert out["verdict"] == "needs_review"
