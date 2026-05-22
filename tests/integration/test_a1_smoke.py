"""A1 졸업: init→status→ls 흐름 (real subprocess)."""
import shutil
import subprocess
from pathlib import Path
import pytest

MIMIRON_BIN = shutil.which("mimiron") or str(
    (Path(__file__).parent.parent.parent / ".venv" / "bin" / "mimiron").resolve()
)


def _run(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [MIMIRON_BIN, *args], cwd=cwd, capture_output=True, text=True, check=False
    )


def test_a1_init_status_ls(tmp_path: Path) -> None:
    cwd = tmp_path
    rc = _run(cwd, "init", "alpha")
    assert rc.returncode == 0, rc.stderr

    rc = _run(cwd, "status", "alpha")
    assert rc.returncode == 0
    assert "alpha" in rc.stdout
    assert "clarify" in rc.stdout

    rc = _run(cwd, "ls")
    assert rc.returncode == 0
    assert "alpha" in rc.stdout
