"""mimiron archive <slug> — finalize 페이즈 종착 (phase=done, persistent=false)."""
import json
from pathlib import Path
import pytest
from mimiron.cli import main
from mimiron.state import State


def _seed_finalize(tmp_project: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_project)
    main(["init", "demo"])
    sidecar = tmp_project / ".mimiron" / "demo"
    state = State.load(sidecar / "state.json")
    state.phase = "finalize"
    state.save(sidecar / "state.json")
    return sidecar


def test_archive_transitions_to_done_and_disables_persist(
    tmp_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sidecar = _seed_finalize(tmp_project, monkeypatch)
    rc = main(["archive", "demo"])
    assert rc == 0
    state = State.load(sidecar / "state.json")
    assert state.phase == "done"
    assert state.persistent is False


def test_archive_creates_marker_file(
    tmp_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sidecar = _seed_finalize(tmp_project, monkeypatch)
    main(["archive", "demo"])
    marker = sidecar / "archive" / "COMPLETED.json"
    assert marker.exists()
    data = json.loads(marker.read_text())
    assert data["slug"] == "demo"
    assert "completed_at" in data
    assert data["final_phase_before_archive"] == "finalize"


def test_archive_rejects_when_phase_not_finalize(
    tmp_project: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_project)
    main(["init", "demo"])
    # phase=clarify (default) — archive 막아야
    rc = main(["archive", "demo"])
    assert rc != 0
    err = capsys.readouterr().err
    assert "finalize" in err


def test_archive_idempotent_on_done_phase(
    tmp_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """한 번 archive 한 후 다시 호출하면 *조용히 OK* (state.phase=done이면)."""
    sidecar = _seed_finalize(tmp_project, monkeypatch)
    main(["archive", "demo"])
    rc = main(["archive", "demo"])
    assert rc == 0
    state = State.load(sidecar / "state.json")
    assert state.phase == "done"


def test_archive_unknown_slug_runtime_error(
    tmp_project: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_project)
    rc = main(["archive", "no-such-slug"])
    assert rc != 0
    err = capsys.readouterr().err
    assert "not" in err.lower()  # "not initialized" or "not found"
