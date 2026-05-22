"""mimiron init <slug> 명령."""
import json
from pathlib import Path
import pytest
from mimiron.cli import main


def test_init_creates_sidecar(tmp_project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_project)
    rc = main(["init", "hello"])
    assert rc == 0
    state_path = tmp_project / ".mimiron" / "hello" / "state.json"
    assert state_path.exists()
    data = json.loads(state_path.read_text())
    assert data["slug"] == "hello"
    assert data["phase"] == "clarify"


def test_init_rejects_existing_slug(tmp_project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_project)
    assert main(["init", "x"]) == 0
    rc = main(["init", "x"])
    assert rc != 0


def test_init_rejects_invalid_slug(tmp_project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_project)
    rc = main(["init", "../escape"])
    assert rc != 0
