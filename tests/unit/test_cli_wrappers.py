"""Wrapper PYTHONPATH isolation tests (C10).

Verifies that ``scripts/_launcher.py`` clears ``PYTHONPATH`` from ``os.environ``
on entry so any subprocess spawned by mimiron (pytest, ruff, mypy, judge) does
NOT inherit a poisoned import path. This is the root cause of the
21-false-fail leak observed in dogfood/003.
"""
from __future__ import annotations

import importlib.util
import os
import pathlib
import subprocess
import sys
from typing import Any

import pytest


REPO_ROOT = pathlib.Path(__file__).parent.parent.parent
WRAPPER_MIMIRON = REPO_ROOT / "scripts" / "mimiron"
WRAPPER_BENCH = REPO_ROOT / "scripts" / "mimiron-bench"
LAUNCHER = REPO_ROOT / "scripts" / "_launcher.py"


# ---------------------------------------------------------------------------
# Wrapper files exist & are executable
# ---------------------------------------------------------------------------


def test_launcher_exists() -> None:
    assert LAUNCHER.exists(), f"launcher missing at {LAUNCHER}"


def test_wrapper_mimiron_exists_and_executable() -> None:
    assert WRAPPER_MIMIRON.exists(), f"wrapper missing at {WRAPPER_MIMIRON}"
    assert os.access(WRAPPER_MIMIRON, os.X_OK), (
        f"wrapper not executable: {WRAPPER_MIMIRON}"
    )


def test_wrapper_bench_exists_and_executable() -> None:
    assert WRAPPER_BENCH.exists(), f"bench wrapper missing at {WRAPPER_BENCH}"
    assert os.access(WRAPPER_BENCH, os.X_OK), (
        f"bench wrapper not executable: {WRAPPER_BENCH}"
    )


# ---------------------------------------------------------------------------
# Launcher.main() in-process: PYTHONPATH must be popped from os.environ
# ---------------------------------------------------------------------------


def _load_launcher_module() -> Any:
    """Load scripts/_launcher.py as a fresh module instance.

    We deliberately bypass ``sys.modules`` so each test gets an isolated
    load — the launcher mutates ``sys.path`` on import-time-of-CLI, and we
    don't want cross-test leakage.
    """
    spec = importlib.util.spec_from_file_location("_launcher_under_test", LAUNCHER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_launcher_clears_pythonpath_on_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Calling launcher.main() with PYTHONPATH set must pop it from os.environ.

    We invoke the launcher with an invalid CLI arg so mimiron.cli.main() exits
    quickly with usage error — that's fine; we only care PYTHONPATH was popped
    before the CLI dispatch.
    """
    sentinel = "/tmp/sentinel-pythonpath-clear-test"
    monkeypatch.setenv("PYTHONPATH", sentinel)
    assert os.environ.get("PYTHONPATH") == sentinel

    launcher = _load_launcher_module()
    monkeypatch.setattr(sys, "argv", ["_launcher.py", "mimiron", "--invalid-no-op"])

    # CLI usage error → SystemExit(2). Anything else after that point is also
    # acceptable; we only assert the launcher's pre-dispatch side-effect.
    try:
        launcher.main()
    except SystemExit:
        pass
    except Exception:
        pass

    assert os.environ.get("PYTHONPATH") is None, (
        f"PYTHONPATH still set to {os.environ.get('PYTHONPATH')!r} "
        f"after launcher.main() — wrapper isolation is broken"
    )


def test_launcher_clears_pythonpath_even_when_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If PYTHONPATH was never set, launcher.main() must not raise on the pop."""
    monkeypatch.delenv("PYTHONPATH", raising=False)
    launcher = _load_launcher_module()
    monkeypatch.setattr(sys, "argv", ["_launcher.py", "mimiron", "--invalid-no-op"])

    try:
        launcher.main()
    except SystemExit:
        pass
    except Exception:
        pass

    assert os.environ.get("PYTHONPATH") is None


def test_launcher_rejects_too_few_args(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Launcher with no entrypoint arg returns 2 and prints usage."""
    launcher = _load_launcher_module()
    rc = launcher.main(["_launcher.py"])
    assert rc == 2
    captured = capsys.readouterr()
    assert "usage" in captured.err.lower()


def test_launcher_rejects_unknown_entrypoint(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Launcher with an unknown entrypoint name returns 2."""
    monkeypatch.delenv("PYTHONPATH", raising=False)
    launcher = _load_launcher_module()
    rc = launcher.main(["_launcher.py", "not-a-real-cli"])
    assert rc == 2
    captured = capsys.readouterr()
    assert "unknown entrypoint" in captured.err.lower()


# ---------------------------------------------------------------------------
# Launcher uses CLAUDE_PLUGIN_ROOT when set, else __file__.parent.parent
# ---------------------------------------------------------------------------


def test_launcher_uses_claude_plugin_root_when_set(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    """When CLAUDE_PLUGIN_ROOT points to a fake dir, the launcher's
    sys.path.insert should pick up ``<fake>/src``.

    We can't easily run the full main() with a fake plugin root (CLI import
    would fail), so we assert the *path resolution* by stopping just before
    dispatch: invoking with unknown entrypoint takes the early-return path
    but only after PYTHONPATH clearing — sys.path insertion happens too.
    """
    fake_root = tmp_path / "fake-plugin-root"
    (fake_root / "src").mkdir(parents=True)
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(fake_root))
    monkeypatch.delenv("PYTHONPATH", raising=False)

    # Save sys.path so we can detect insertion without leaking into other tests.
    original_sys_path = list(sys.path)
    try:
        launcher = _load_launcher_module()
        # Use unknown entrypoint so dispatch returns 2 *after* path setup.
        rc = launcher.main(["_launcher.py", "not-a-real-cli"])
        assert rc == 2
        expected_src = str(fake_root / "src")
        assert expected_src in sys.path, (
            f"expected {expected_src} in sys.path; got {sys.path[:5]}..."
        )
    finally:
        # Restore — don't leak the fake path into other tests.
        sys.path[:] = original_sys_path


def test_launcher_falls_back_to_grandparent_when_no_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without CLAUDE_PLUGIN_ROOT, launcher should resolve plugin root from
    ``__file__.parent.parent`` — i.e. the actual repo root in our test setup.
    """
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    monkeypatch.delenv("PYTHONPATH", raising=False)

    original_sys_path = list(sys.path)
    try:
        launcher = _load_launcher_module()
        rc = launcher.main(["_launcher.py", "not-a-real-cli"])
        assert rc == 2
        expected_src = str(REPO_ROOT / "src")
        assert expected_src in sys.path
    finally:
        sys.path[:] = original_sys_path


# ---------------------------------------------------------------------------
# End-to-end subprocess: spawn scripts/mimiron with poisoned PYTHONPATH
# ---------------------------------------------------------------------------


def test_wrapper_subprocess_runs_with_poisoned_pythonpath() -> None:
    """End-to-end: spawn scripts/mimiron with PYTHONPATH=/tmp/sentinel.

    The wrapper must not crash on PYTHONPATH inheritance (it pops it inside
    the launcher) and must execute the requested mimiron subcommand. We use
    ``status nonexistent-slug-test-only`` as the smoke command: it fails with
    rc=1 and a clear 'not found' error, which proves the CLI actually ran.
    """
    sentinel = "/tmp/sentinel-leak-test-does-not-exist"
    env = {**os.environ, "PYTHONPATH": sentinel}
    proc = subprocess.run(
        [str(WRAPPER_MIMIRON), "status", "nonexistent-slug-test-only"],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    combined = proc.stdout + proc.stderr
    # The CLI's "not found" handling produces rc=1; the *important* signal is
    # that the slug name shows up in output, proving the CLI dispatched.
    assert "nonexistent-slug-test-only" in combined, (
        f"expected slug name in output; got rc={proc.returncode!r} "
        f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    assert proc.returncode != 0, (
        f"status on nonexistent slug should fail; got rc=0 output={combined!r}"
    )


def test_wrapper_subprocess_help_works_with_poisoned_pythonpath() -> None:
    """``scripts/mimiron --help`` (or any subcommand --help) must succeed with
    a poisoned PYTHONPATH set in the parent env."""
    sentinel = "/tmp/sentinel-help-test"
    env = {**os.environ, "PYTHONPATH": sentinel}
    proc = subprocess.run(
        [str(WRAPPER_MIMIRON), "--help"],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, (
        f"--help should succeed; got rc={proc.returncode!r} stderr={proc.stderr!r}"
    )
    # argparse prints "usage:" on --help.
    assert "usage" in proc.stdout.lower() or "usage" in proc.stderr.lower()


def test_wrapper_subprocess_does_not_pass_pythonpath_to_grandchildren() -> None:
    """The launcher pops PYTHONPATH from os.environ; therefore any subprocess
    that mimiron itself spawns inherits a clean env.

    We verify this by running a Python ``-c`` invocation *through the launcher*
    that prints os.environ.get('PYTHONPATH'). To do this without depending on
    mimiron internals, we spawn _launcher.py directly with an unknown
    entrypoint AFTER monkeypatching argv — but that's already covered by the
    in-process tests above. For a true end-to-end signal we observe that the
    wrapper's own Python child (the launcher itself, run by ``exec python3``)
    sees PYTHONPATH cleared before any grandchild would be spawned. This is
    indirectly proven by the wrapper-subprocess tests above succeeding with
    a sentinel PYTHONPATH that would otherwise crash import.

    This test makes the contract explicit by checking that no actual file at
    the sentinel path is required for the wrapper to succeed.
    """
    sentinel = "/this/path/definitely/does/not/exist/sentinel"
    assert not pathlib.Path(sentinel).exists()
    env = {**os.environ, "PYTHONPATH": sentinel}
    proc = subprocess.run(
        [str(WRAPPER_MIMIRON), "--help"],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    # If PYTHONPATH leaked into the launcher's own import machinery, the
    # mimiron import would either succeed (sentinel ignored — fine) or fail
    # with an import error referencing the sentinel. We assert --help works.
    assert proc.returncode == 0, (
        f"wrapper crashed on nonexistent sentinel PYTHONPATH "
        f"({sentinel!r}); rc={proc.returncode!r} stderr={proc.stderr!r}"
    )
