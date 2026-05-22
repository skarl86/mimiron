"""mimiron pause / resume — state.paused 토글."""
from pathlib import Path
import pytest
from mimiron.cli import main
from mimiron.state import State


def test_pause_marks_paused_true(
    tmp_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_project)
    main(["init", "demo"])
    rc = main(["pause", "demo"])
    assert rc == 0
    state = State.load(tmp_project / ".mimiron" / "demo" / "state.json")
    assert state.paused is True


def test_pause_idempotent_on_already_paused(
    tmp_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_project)
    main(["init", "demo"])
    main(["pause", "demo"])
    rc = main(["pause", "demo"])
    assert rc == 0
    state = State.load(tmp_project / ".mimiron" / "demo" / "state.json")
    assert state.paused is True


def test_resume_clears_paused_flag(
    tmp_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_project)
    main(["init", "demo"])
    main(["pause", "demo"])
    rc = main(["resume", "demo"])
    assert rc == 0
    state = State.load(tmp_project / ".mimiron" / "demo" / "state.json")
    assert state.paused is False


def test_resume_rejects_stuck_phase(
    tmp_project: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """phase=stuck면 unstuck 경로를 거쳐야 하지 단순 resume으로 못 풀음."""
    monkeypatch.chdir(tmp_project)
    main(["init", "demo"])
    sidecar = tmp_project / ".mimiron" / "demo"
    state = State.load(sidecar / "state.json")
    state.phase = "stuck"
    state.paused = True
    state.save(sidecar / "state.json")
    rc = main(["resume", "demo"])
    assert rc != 0
    err = capsys.readouterr().err
    assert "stuck" in err.lower() or "unstuck" in err.lower()


def test_resume_rejects_done_phase(
    tmp_project: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_project)
    main(["init", "demo"])
    sidecar = tmp_project / ".mimiron" / "demo"
    state = State.load(sidecar / "state.json")
    state.phase = "done"
    state.save(sidecar / "state.json")
    rc = main(["resume", "demo"])
    assert rc != 0


def test_pause_unknown_slug_runtime_error(
    tmp_project: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_project)
    rc = main(["pause", "no-such"])
    assert rc != 0


def test_resume_unknown_slug_runtime_error(
    tmp_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_project)
    rc = main(["resume", "no-such"])
    assert rc != 0
