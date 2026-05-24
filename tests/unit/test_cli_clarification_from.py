"""mimiron init --clarification-from <file> — clarify phase skip + state injection."""
from __future__ import annotations

import json


def test_init_with_clarification_jumps_to_spec_phase(tmp_path, monkeypatch):
    from mimiron import cli

    monkeypatch.chdir(tmp_path)
    src = tmp_path / "issue.md"
    src.write_text("Allow non-ASCII username validation.\n\nExpected: validator accepts é, ü.\n")

    rc = cli.main([
        "init", "swebench-django-11099",
        "--clarification-from", str(src),
        "--no-persist",
    ])
    assert rc == 0
    sidecar = tmp_path / ".mimiron" / "swebench-django-11099"
    assert sidecar.exists()
    state = json.loads((sidecar / "state.json").read_text())
    assert state["phase"] == "spec"
    clar = sidecar / "clarification.md"
    assert clar.exists()
    assert "non-ASCII username" in clar.read_text()


def test_init_clarification_file_missing_returns_usage_error(tmp_path, monkeypatch):
    from mimiron import cli

    monkeypatch.chdir(tmp_path)
    rc = cli.main([
        "init", "x",
        "--clarification-from", str(tmp_path / "nope.md"),
    ])
    assert rc == 2


def test_init_without_clarification_still_starts_at_clarify(tmp_path, monkeypatch):
    """Regression: 기존 동작 안 깨짐."""
    from mimiron import cli

    monkeypatch.chdir(tmp_path)
    rc = cli.main(["init", "regular-slug", "--no-persist"])
    assert rc == 0
    state = json.loads((tmp_path / ".mimiron" / "regular-slug" / "state.json").read_text())
    assert state["phase"] == "clarify"
