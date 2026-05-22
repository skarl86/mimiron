"""A3 졸업: init → plan → 가짜 워커 산출 → commit-task → gate mechanical."""
import json
import shutil
import subprocess
from pathlib import Path
from mimiron.hash_util import sha256_file


MIMIRON_BIN = shutil.which("mimiron") or str(
    (Path(__file__).parent.parent.parent / ".venv" / "bin" / "mimiron").resolve()
)


def _setup_global(cwd: Path, mechanical_body: str) -> None:
    (cwd / ".mimiron" / "_global").mkdir(parents=True, exist_ok=True)
    (cwd / ".mimiron" / "_global" / "mechanical.toml").write_text(mechanical_body)


def test_a3_full_loop(tmp_path: Path) -> None:
    fixtures = Path(__file__).parent.parent / "fixtures"
    subprocess.run([MIMIRON_BIN, "init", "demo"], cwd=tmp_path, check=True)
    sidecar = tmp_path / ".mimiron" / "demo"
    shutil.copy(fixtures / "plans" / "diamond.yaml", sidecar / "plan.yaml")

    # 가짜 워커: root.py 생성
    root = tmp_path / "root.py"
    root.write_text("print('root')\n")
    art = sidecar / "tasks" / "T01" / "artifacts.json"
    art.parent.mkdir(parents=True)
    art.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "task_id": "T01",
                "declared_files": [
                    {
                        "path": "root.py",
                        "action": "create",
                        "pre_hash": None,
                        "post_hash": sha256_file(root),
                        "pre_mtime": None,
                        "post_mtime": "2026-05-22T00:00:00Z",
                    }
                ],
                "worker_summary": "ok",
            }
        )
    )

    rc = subprocess.run(
        [MIMIRON_BIN, "commit-task", "demo", "T01"], cwd=tmp_path, check=False
    )
    assert rc.returncode == 0

    # mechanical gate pass
    _setup_global(tmp_path, '[[checks]]\nname = "echo"\ncommand = "echo ok"\ntimeout_s = 5\n')
    rc = subprocess.run(
        [MIMIRON_BIN, "gate", "demo", "mechanical"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert rc.returncode == 0
    assert "pass" in rc.stdout
