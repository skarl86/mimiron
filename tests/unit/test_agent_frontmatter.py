"""agent 파일의 YAML frontmatter 검증."""
from pathlib import Path
import yaml


AGENT_PATHS = [
    Path("agents/mimiron-reviewer.md"),
]


def _frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{path}: missing frontmatter"
    end = text.index("\n---\n", 4)
    return yaml.safe_load(text[4:end])


def test_reviewer_agent_frontmatter_has_required_fields() -> None:
    fm = _frontmatter(AGENT_PATHS[0])
    assert fm["name"] == "mimiron-reviewer"
    assert len(fm["description"]) > 50
    assert "tools" in fm and isinstance(fm["tools"], list)


def test_reviewer_agent_has_no_write_tools() -> None:
    """spec § 4.4: mimiron-reviewer는 *코드 수정 절대 금지*.
    Write/Edit/Bash (실행) tool이 list에 *있으면* 위반.
    """
    fm = _frontmatter(AGENT_PATHS[0])
    tools = set(fm["tools"])
    forbidden = {"Write", "Edit", "MultiEdit", "Bash", "NotebookEdit"}
    overlap = tools & forbidden
    assert not overlap, (
        f"reviewer agent has forbidden write-tools: {overlap}. "
        "Spec § 4.4 requires read-only judgment."
    )
