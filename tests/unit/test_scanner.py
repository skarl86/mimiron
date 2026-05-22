"""DAG scanner."""
from pathlib import Path
from mimiron.plan import Plan
from mimiron.scanner import scan


def test_scan_initial(fixtures_dir: Path) -> None:
    plan = Plan.load(fixtures_dir / "plans" / "diamond.yaml")
    result = scan(plan, completed_ids=[], in_flight_ids=[])
    assert set(result.ready) == {"T01"}
    assert result.in_flight == []
    assert set(result.pending) == {"T02", "T03", "T04"}
    assert result.phase_done is False


def test_scan_after_root(fixtures_dir: Path) -> None:
    plan = Plan.load(fixtures_dir / "plans" / "diamond.yaml")
    result = scan(plan, completed_ids=["T01"], in_flight_ids=[])
    assert set(result.ready) == {"T02", "T03"}
    assert set(result.pending) == {"T04"}


def test_scan_all_done(fixtures_dir: Path) -> None:
    plan = Plan.load(fixtures_dir / "plans" / "diamond.yaml")
    result = scan(plan, completed_ids=["T01", "T02", "T03", "T04"], in_flight_ids=[])
    assert result.ready == []
    assert result.in_flight == []
    assert result.pending == []
    assert result.phase_done is True


def test_scan_excludes_in_flight_owned_file_conflicts(fixtures_dir: Path) -> None:
    plan = Plan.load(fixtures_dir / "plans" / "diamond.yaml")
    result = scan(plan, completed_ids=["T01"], in_flight_ids=["T02"])
    assert "T03" in result.ready  # T03은 T02와 파일 안 겹침
    assert result.in_flight == ["T02"]
