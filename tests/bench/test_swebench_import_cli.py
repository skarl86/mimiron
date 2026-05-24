"""mimiron-bench swebench import — CLI integration."""
from __future__ import annotations

from pathlib import Path


def test_swebench_import_creates_stratified_fixtures(tmp_path, monkeypatch):
    from mimiron.bench import cli as bench_cli

    monkeypatch.chdir(tmp_path)
    src = Path(__file__).parent.parent / "fixtures" / "swebench_sample.jsonl"

    rc = bench_cli.main([
        "swebench", "import",
        "--from-jsonl", str(src),
        "--stratified", "3",
        "--seed", "42",
    ])
    assert rc == 0
    created = sorted((tmp_path / "benchmarks").glob("SWE-LITE-*"))
    assert len(created) == 3
    assert all((d / "benchmark.yaml").exists() for d in created)
    assert all((d / "issue.md").exists() for d in created)


def test_swebench_import_refuses_without_source(tmp_path, monkeypatch):
    from mimiron.bench import cli as bench_cli

    monkeypatch.chdir(tmp_path)
    rc = bench_cli.main(["swebench", "import", "--stratified", "3"])
    assert rc == 2  # usage error


def test_swebench_import_missing_jsonl_returns_clean_error(tmp_path, monkeypatch, capsys):
    from mimiron.bench import cli as bench_cli

    monkeypatch.chdir(tmp_path)
    rc = bench_cli.main([
        "swebench", "import",
        "--from-jsonl", str(tmp_path / "nonexistent.jsonl"),
        "--stratified", "3",
    ])
    assert rc == 2
    captured = capsys.readouterr()
    assert "error" in captured.err.lower()
    assert "nonexistent.jsonl" in captured.err or "No such file" in captured.err
