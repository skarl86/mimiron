"""mimiron scan <slug>."""
import json
import shutil
from pathlib import Path
import pytest
from mimiron.cli import main


def test_scan_returns_json(
    capsys: pytest.CaptureFixture[str],
    tmp_project: Path,
    monkeypatch: pytest.MonkeyPatch,
    fixtures_dir: Path,
) -> None:
    monkeypatch.chdir(tmp_project)
    main(["init", "demo"])
    shutil.copy(
        fixtures_dir / "plans" / "diamond.yaml",
        tmp_project / ".mimiron" / "demo" / "plan.yaml",
    )
    capsys.readouterr()
    rc = main(["scan", "demo"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert "ready" in out and "pending" in out and "phase_done" in out
    assert "T01" in out["ready"]


def test_scan_missing_plan_fails(
    tmp_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_project)
    main(["init", "x"])
    assert main(["scan", "x"]) != 0
