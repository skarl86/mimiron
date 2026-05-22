"""A2 졸업: init → plan.yaml 배치 → scan."""
import json
import shutil
import subprocess
from pathlib import Path

MIMIRON_BIN = shutil.which("mimiron") or str(
    (Path(__file__).parent.parent.parent / ".venv" / "bin" / "mimiron").resolve()
)


def test_a2_scan_diamond(tmp_path: Path) -> None:
    fixtures = Path(__file__).parent.parent / "fixtures" / "plans"
    subprocess.run([MIMIRON_BIN, "init", "diamond"], cwd=tmp_path, check=True)
    sidecar = tmp_path / ".mimiron" / "diamond"
    shutil.copy(fixtures / "diamond.yaml", sidecar / "plan.yaml")
    rc = subprocess.run(
        [MIMIRON_BIN, "scan", "diamond"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    out = json.loads(rc.stdout)
    assert "T01" in out["ready"]
    assert "T04" in out["pending"]
