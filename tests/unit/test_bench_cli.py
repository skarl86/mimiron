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


def test_run_with_similarity_from_missing_file_exits_2(
    bench_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(bench_root)
    rc = main(["run", "B00-toy", "--similarity-from", "no-such.json"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "judge file" in err


def test_run_with_similarity_from_malformed_exits_2(
    bench_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(bench_root)
    bad = bench_root / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    rc = main(["run", "B00-toy", "--similarity-from", "bad.json"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "judge file" in err


def test_list_json_emits_valid_array_for_populated(
    bench_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(bench_root)
    rc = main(["list", "--json"])
    assert rc == 0
    out = capsys.readouterr().out
    arr = json.loads(out)
    assert isinstance(arr, list)
    assert len(arr) >= 1
    for entry in arr:
        assert set(entry) >= {"id", "difficulty", "status"}
        assert isinstance(entry["id"], str)
        assert isinstance(entry["difficulty"], str)
        assert isinstance(entry["status"], str)


def test_list_json_empty_returns_empty_array(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """benchmarks/ 자체가 없거나 비어있으면 JSON은 []."""
    monkeypatch.chdir(tmp_path)
    rc = main(["list", "--json"])
    assert rc == 0
    out = capsys.readouterr().out
    arr = json.loads(out)
    assert arr == []


def test_list_without_json_preserves_table_header(
    bench_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """회귀: --json 없이는 기존 사람용 표 헤더가 그대로."""
    monkeypatch.chdir(bench_root)
    rc = main(["list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "ID" in out
    assert "DIFFICULTY" in out
    assert "STATUS" in out


def test_list_json_corrupted_benchmark_yields_corrupted_row(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """benchmark.yaml에 필수 필드 누락이면 JSON에 status=corrupted 행 한 줄."""
    bench_dir = tmp_path / "benchmarks" / "broken"
    bench_dir.mkdir(parents=True)
    (bench_dir / "benchmark.yaml").write_text("id: broken\n")  # 필수 필드 누락
    monkeypatch.chdir(tmp_path)
    rc = main(["list", "--json"])
    assert rc == 0
    arr = json.loads(capsys.readouterr().out)
    assert any(e.get("status") == "corrupted" for e in arr)
