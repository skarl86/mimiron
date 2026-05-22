"""mimiron gate <slug> ambiguity (clarification.md + 점수 입력으로 verdict)."""
import json
from pathlib import Path
import pytest
from mimiron.cli import main


def _setup(tmp_project: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_project)
    main(["init", "demo"])
    sidecar = tmp_project / ".mimiron" / "demo"
    (sidecar / "clarification.md").write_text(
        "---\nslug: demo\nambiguity_score: 0.10\nsamples: [0.08, 0.10, 0.12]\n---\n\n# x\n"
    )
    return sidecar


def test_ambiguity_gate_passes(
    tmp_project: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _setup(tmp_project, monkeypatch)
    capsys.readouterr()
    rc = main(["gate", "demo", "ambiguity"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["verdict"] == "pass"
    assert abs(out["score"] - 0.10) < 0.001


def test_ambiguity_gate_certainty_band_needs_review(
    tmp_project: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sidecar = _setup(tmp_project, monkeypatch)
    (sidecar / "clarification.md").write_text(
        "---\nslug: demo\nambiguity_score: 0.22\nsamples: [0.20, 0.22, 0.24]\n---\n\n# x\n"
    )
    capsys.readouterr()
    main(["gate", "demo", "ambiguity"])
    out = json.loads(capsys.readouterr().out)
    assert out["verdict"] == "needs_review"


def test_ambiguity_gate_fails_when_too_high(
    tmp_project: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sidecar = _setup(tmp_project, monkeypatch)
    (sidecar / "clarification.md").write_text(
        "---\nslug: demo\nambiguity_score: 0.40\nsamples: [0.38, 0.40, 0.42]\n---\n\n# x\n"
    )
    capsys.readouterr()
    rc = main(["gate", "demo", "ambiguity"])
    out = json.loads(capsys.readouterr().out)
    assert out["verdict"] == "fail"
    assert rc != 0
