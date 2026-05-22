"""bench compare + suite."""
import json
from pathlib import Path
import pytest
from mimiron.bench.cli import main


def test_compare_emits_diff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    d1 = tmp_path / "before"
    d2 = tmp_path / "after"
    d1.mkdir()
    d2.mkdir()
    (d1 / "B01.json").write_text(json.dumps({"bench_score": 0.5}))
    (d2 / "B01.json").write_text(json.dumps({"bench_score": 0.8}))
    rc = main(["compare", "before", "after"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "B01" in out
    assert "+0.300" in out


def test_suite_empty_when_no_benchmarks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    rc = main(["suite"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["benchmarks"] == 0
    assert out["suite_aggregate"] is None
