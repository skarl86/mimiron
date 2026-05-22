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


def test_load_empty_file_raises_plan_error(tmp_path: Path) -> None:
    p = tmp_path / "plan.yaml"
    p.write_text("", encoding="utf-8")
    with pytest.raises(PlanError, match="empty|schema_version"):
        Plan.load(p)


def test_load_missing_slug_raises_plan_error(tmp_path: Path) -> None:
    p = tmp_path / "plan.yaml"
    p.write_text("schema_version: 1\nspec_hash: x\ntasks: []\n", encoding="utf-8")
    with pytest.raises(PlanError, match="slug"):
        Plan.load(p)


def test_load_missing_spec_hash_raises_plan_error(tmp_path: Path) -> None:
    p = tmp_path / "plan.yaml"
    p.write_text("schema_version: 1\nslug: x\ntasks: []\n", encoding="utf-8")
    with pytest.raises(PlanError, match="spec_hash"):
        Plan.load(p)


def test_load_missing_tasks_raises_plan_error(tmp_path: Path) -> None:
    p = tmp_path / "plan.yaml"
    p.write_text("schema_version: 1\nslug: x\nspec_hash: y\n", encoding="utf-8")
    with pytest.raises(PlanError, match="tasks"):
        Plan.load(p)


def test_load_task_missing_id_raises_plan_error(tmp_path: Path) -> None:
    p = tmp_path / "plan.yaml"
    p.write_text(
        "schema_version: 1\nslug: x\nspec_hash: y\n"
        "tasks:\n  - title: t\n",
        encoding="utf-8",
    )
    with pytest.raises(PlanError, match="id"):
        Plan.load(p)


def test_load_task_missing_title_raises_plan_error(tmp_path: Path) -> None:
    p = tmp_path / "plan.yaml"
    p.write_text(
        "schema_version: 1\nslug: x\nspec_hash: y\n"
        "tasks:\n  - id: T01\n",
        encoding="utf-8",
    )
    with pytest.raises(PlanError, match="title"):
        Plan.load(p)
