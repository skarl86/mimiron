"""bench run 흐름 (similarity_provider 없이 deferred 반환 확인)."""
import json
import shutil
import subprocess
from pathlib import Path
import pytest


@pytest.fixture
def bench_project(tmp_path: Path) -> Path:
    """benchmarks/B00-toy 가 있는 가짜 프로젝트."""
    fixtures = Path(__file__).parent.parent / "fixtures" / "benchmarks" / "B00-toy"
    proj = tmp_path / "proj"
    proj.mkdir()
    shutil.copytree(fixtures, proj / "benchmarks" / "B00-toy")
    (proj / "benchmarks" / "_cutoff.yaml").write_text(
        "schema_version: 1\ncutoff_case: 0.75\ncutoff_global: 0.75\n"
        "w_test: 0.6\nw_sim: 0.4\ncertainty_band: 0.05\n"
    )
    # toy_repo (benchmark.repo가 가리키는)는 가벼운 git 초기화
    toy = proj / "benchmarks" / "B00-toy" / "toy_repo"
    toy.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=toy, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=toy, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=toy, check=True)
    (toy / "a.txt").write_text("v1\n")
    subprocess.run(["git", "add", "."], cwd=toy, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "c1"], cwd=toy, check=True, capture_output=True)
    (toy / "toy.txt").write_text("toy")
    subprocess.run(["git", "add", "."], cwd=toy, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "c2"], cwd=toy, check=True, capture_output=True)
    return proj


def test_bench_run_returns_verdict(bench_project: Path) -> None:
    import shutil as _sh
    bin_path = _sh.which("mimiron-bench") or str(
        (Path(__file__).parent.parent.parent / ".venv" / "bin" / "mimiron-bench").resolve()
    )
    rc = subprocess.run(
        [bin_path, "run", "B00-toy"],
        cwd=bench_project,
        capture_output=True,
        text=True,
        check=False,
    )
    assert rc.returncode in {0, 1}, rc.stderr
    v = json.loads(rc.stdout)
    assert v["id"] == "B00-toy"
    assert "status" in v
    # similarity_provider 없으므로 deferred
    assert v["status"] == "deferred"
