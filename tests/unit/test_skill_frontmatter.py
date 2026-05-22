"""skill 파일의 YAML frontmatter 검증."""
from pathlib import Path
import yaml


SKILL_PATHS = [
    Path("skills/clarify/SKILL.md"),
    Path("skills/spec/SKILL.md"),
    Path("skills/bench-judge/SKILL.md"),
]


def _frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{path}: missing frontmatter"
    end = text.index("\n---\n", 4)
    return yaml.safe_load(text[4:end])


def test_clarify_skill_frontmatter_has_required_fields() -> None:
    fm = _frontmatter(SKILL_PATHS[0])
    assert "name" in fm and fm["name"] == "mimiron-clarify"
    assert "description" in fm
    assert len(fm["description"]) > 50


def test_spec_skill_frontmatter_has_required_fields() -> None:
    fm = _frontmatter(SKILL_PATHS[1])
    assert fm["name"] == "mimiron-spec"
    assert len(fm["description"]) > 50


def test_bench_judge_skill_frontmatter_has_required_fields() -> None:
    fm = _frontmatter(SKILL_PATHS[2])
    assert fm["name"] == "mimiron-bench-judge"
    assert len(fm["description"]) > 50
