"""End-to-end lifecycle for user_language:
init with --language → state persisted → status surfaces it → resume preserves it.

We can't drive the actual Skill tool from pytest (that's a Claude-runtime concern),
but we *can* verify the CLI contract that every skill depends on:

  1. `mimiron init --language Korean` writes Korean into state.json
  2. `mimiron status` (text + --json) surfaces the value
  3. State.load() round-trips the value, so any skill that does
     `State.load(.mimiron/<slug>/state.json)` sees the same string
  4. Legacy state.json files (pre-feature, no user_language key) still load
     with user_language=None — no migration required
"""
import json
import shutil
import subprocess
from pathlib import Path


_VENV_BIN = (Path(__file__).parent.parent.parent / ".venv" / "bin" / "mimiron").resolve()
# Prefer the project venv — `shutil.which` can resolve a stale global install
# (e.g. pipx) that lags behind the source tree under test.
MIMIRON_BIN = str(_VENV_BIN) if _VENV_BIN.exists() else shutil.which("mimiron")


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [MIMIRON_BIN, *args], cwd=cwd, capture_output=True, text=True, check=False
    )


def test_init_with_language_persists_through_status_and_load(tmp_path: Path) -> None:
    init = _run(["init", "ko-run", "--language", "Korean"], tmp_path)
    assert init.returncode == 0, init.stderr

    state_path = tmp_path / ".mimiron" / "ko-run" / "state.json"
    raw = json.loads(state_path.read_text(encoding="utf-8"))
    assert raw["user_language"] == "Korean"

    status = _run(["status", "ko-run"], tmp_path)
    assert status.returncode == 0
    assert "Korean" in status.stdout
    assert "language:" in status.stdout

    status_json = _run(["status", "ko-run", "--json"], tmp_path)
    obj = json.loads(status_json.stdout)
    assert obj["user_language"] == "Korean"


def test_init_without_language_persists_null_and_status_shows_auto(tmp_path: Path) -> None:
    init = _run(["init", "auto-run"], tmp_path)
    assert init.returncode == 0, init.stderr

    raw = json.loads((tmp_path / ".mimiron" / "auto-run" / "state.json").read_text())
    assert raw["user_language"] is None

    status = _run(["status", "auto-run"], tmp_path)
    assert "auto" in status.stdout


def test_arbitrary_language_string_round_trips(tmp_path: Path) -> None:
    """user_language is intentionally free-form so users can pick languages we
    haven't enumerated. This locks that down so a future contributor doesn't
    turn it into a strict enum without thinking."""
    init = _run(["init", "ja-run", "--language", "日本語"], tmp_path)
    assert init.returncode == 0, init.stderr
    raw = json.loads((tmp_path / ".mimiron" / "ja-run" / "state.json").read_text())
    assert raw["user_language"] == "日本語"


def test_legacy_state_without_user_language_field_still_loads(tmp_path: Path) -> None:
    """Existing slugs created before this feature must continue to work without
    a manual migration. State.load drops unknown keys *and* defaults missing
    optional keys, so removing user_language from raw json should be safe."""
    init = _run(["init", "legacy", "--language", "Korean"], tmp_path)
    assert init.returncode == 0, init.stderr
    state_path = tmp_path / ".mimiron" / "legacy" / "state.json"
    raw = json.loads(state_path.read_text())
    del raw["user_language"]
    state_path.write_text(json.dumps(raw))

    status = _run(["status", "legacy"], tmp_path)
    assert status.returncode == 0, status.stderr
    assert "auto" in status.stdout  # missing field → None → "auto"
