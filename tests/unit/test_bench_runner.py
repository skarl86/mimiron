"""bench Benchmark 로딩."""
from pathlib import Path
import pytest
from mimiron.bench.runner import Benchmark, BenchmarkError


def test_load_toy(fixtures_dir: Path) -> None:
    b = Benchmark.load(fixtures_dir / "benchmarks" / "B00-toy" / "benchmark.yaml")
    assert b.id == "B00-toy"
    assert b.difficulty == "easy"
    assert b.test_command == "echo ok"


def test_load_rejects_missing_required(tmp_path: Path) -> None:
    p = tmp_path / "bench.yaml"
    p.write_text("id: x\n")
    with pytest.raises(BenchmarkError):
        Benchmark.load(p)
