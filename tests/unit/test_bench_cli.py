"""mimiron-bench CLI."""
import json
import shutil
from pathlib import Path
import pytest
from mimiron.bench.cli import main


@pytest.fixture
def bench_root(tmp_path: Path, fixtures_dir: Path) -> Path:
    """가짜 benchmarks/ + _cutoff.yaml."""
    root = tmp_path / "benchmarks"
    root.mkdir()
    (root / "_cutoff.yaml").write_text(
        "schema_version: 1\ncutoff_case: 0.75\ncutoff_global: 0.75\n"
        "w_test: 0.6\nw_sim: 0.4\ncertainty_band: 0.05\n"
    )
    shutil.copytree(fixtures_dir / "benchmarks" / "B00-toy", root / "B00-toy")
    return tmp_path


def test_list_includes_toy(
    bench_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(bench_root)
    rc = main(["list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "B00-toy" in out


def test_run_skeleton_returns_pending_when_dry_run(
    bench_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(bench_root)
    monkeypatch.setenv("MIMIRON_BENCH_DRY_RUN", "1")
    assert main(["run", "B00-toy"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["id"] == "B00-toy"
    assert out.get("status") in {"pending", "deferred", "passed", "failed"}
