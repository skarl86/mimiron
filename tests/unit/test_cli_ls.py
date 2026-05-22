"""mimiron ls 명령."""
from pathlib import Path
import pytest
from mimiron.cli import main


def test_ls_empty(
    capsys: pytest.CaptureFixture[str],
    tmp_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_project)
    assert main(["ls"]) == 0
    out = capsys.readouterr().out
    assert "no slugs" in out.lower()


def test_ls_lists_slugs_with_phase(
    capsys: pytest.CaptureFixture[str],
    tmp_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_project)
    main(["init", "alpha"])
    main(["init", "beta"])
    capsys.readouterr()
    assert main(["ls"]) == 0
    out = capsys.readouterr().out
    assert "alpha" in out and "beta" in out
    assert "clarify" in out
