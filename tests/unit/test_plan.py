"""plan.yaml 모델."""
from pathlib import Path
import pytest
from mimiron.plan import Plan, PlanError


def test_load_diamond(fixtures_dir: Path) -> None:
    plan = Plan.load(fixtures_dir / "plans" / "diamond.yaml")
    assert plan.slug == "diamond"
    assert plan.spec_hash == "deadbeef"
    assert len(plan.tasks) == 4
    by_id = {t.id: t for t in plan.tasks}
    assert by_id["T04"].depends_on == ["T02", "T03"]


def test_detect_cycle(fixtures_dir: Path) -> None:
    with pytest.raises(PlanError, match="cycle"):
        Plan.load(fixtures_dir / "plans" / "cycle.yaml").validate()


def test_detect_file_ownership_conflict(fixtures_dir: Path) -> None:
    plan = Plan.load(fixtures_dir / "plans" / "conflict.yaml")
    with pytest.raises(PlanError, match="owned_files"):
        plan.validate()


def test_worker_defaults_to_worker(fixtures_dir: Path) -> None:
    plan = Plan.load(fixtures_dir / "plans" / "diamond.yaml")
    assert all(t.worker in {"worker", "tester", "reviewer"} for t in plan.tasks)
