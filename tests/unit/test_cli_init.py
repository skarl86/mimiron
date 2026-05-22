"""mimiron init <slug> 명령."""
import json
from pathlib import Path
import pytest
from mimiron.cli import main, EXIT_RUNTIME_ERROR, EXIT_USAGE_ERROR


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


def test_init_rejects_existing_slug_with_runtime_code(
    tmp_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_project)
    main(["init", "y"])
    rc = main(["init", "y"])
    assert rc == EXIT_RUNTIME_ERROR


def test_init_rejects_invalid_slug_with_usage_code(
    tmp_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_project)
    rc = main(["init", "../escape"])
    assert rc == EXIT_USAGE_ERROR
