"""mimiron status <slug>."""
import json
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


def test_status_json_emits_valid_object(
    capsys: pytest.CaptureFixture[str],
    tmp_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_project)
    main(["init", "demo"])
    capsys.readouterr()
    rc = main(["status", "demo", "--json"])
    assert rc == 0
    obj = json.loads(capsys.readouterr().out)
    assert isinstance(obj, dict)
    expected = {
        "slug", "phase", "persistent", "paused", "retries",
        "gate_count", "consecutive_gate_fails", "token_usage", "updated_at",
    }
    assert expected <= set(obj)
    assert obj["slug"] == "demo"
    assert obj["phase"] == "clarify"
    assert obj["persistent"] is True
    assert obj["paused"] is False


def test_status_without_json_preserves_ascii_tree(
    capsys: pytest.CaptureFixture[str],
    tmp_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """회귀: --json 없으면 기존 ASCII 트리 그대로 (banner + ├─/└─ 형식)."""
    monkeypatch.chdir(tmp_project)
    main(["init", "demo"])
    capsys.readouterr()
    main(["status", "demo"])
    out = capsys.readouterr().out
    assert "persistent" in out
    assert "├─" in out or "└─" in out  # ASCII 트리 형식


def test_status_json_missing_slug_nonzero(
    tmp_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """slug 없으면 --json 모드여도 exit !=0."""
    monkeypatch.chdir(tmp_project)
    rc = main(["status", "ghost", "--json"])
    assert rc != 0
