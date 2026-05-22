"""mimiron status <slug>."""
from pathlib import Path
import pytest
from mimiron.cli import main


def test_status_missing_slug_returns_nonzero(
    tmp_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_project)
    assert main(["status", "ghost"]) != 0


def test_status_renders_phase(
    capsys: pytest.CaptureFixture[str],
    tmp_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_project)
    main(["init", "demo"])
    capsys.readouterr()
    assert main(["status", "demo"]) == 0
    out = capsys.readouterr().out
    assert "demo" in out
    assert "phase" in out.lower()
    assert "clarify" in out
    assert "persistent" in out.lower()
