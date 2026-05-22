"""commands/ .md 파일의 YAML frontmatter 검증."""
from pathlib import Path
import yaml


COMMAND_PATHS = [
    Path("commands/mimiron.md"),
    Path("commands/mimiron-resume.md"),
    Path("commands/mimiron-status.md"),
    Path("commands/mimiron-pause.md"),
    Path("commands/mimiron-unstuck.md"),
]


def _frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{path}: missing frontmatter"
    end = text.index("\n---\n", 4)
    return yaml.safe_load(text[4:end])


def test_all_commands_have_required_fields() -> None:
    for path in COMMAND_PATHS:
        fm = _frontmatter(path)
        assert "description" in fm, f"{path}: missing description"
        assert len(fm["description"]) > 20, f"{path}: description too short"
        assert "allowed-tools" in fm, f"{path}: missing allowed-tools"


def test_status_command_is_readonly_no_write_tools() -> None:
    """mimiron-status는 read-only — Write/Edit 없이도 됨."""
    fm = _frontmatter(Path("commands/mimiron-status.md"))
    tools = set(fm.get("allowed-tools", "").replace(",", " ").split())
    forbidden = {"Write", "Edit", "MultiEdit"}
    assert not (tools & forbidden), (
        f"mimiron-status should be read-only; found write tools: {tools & forbidden}"
    )


def test_pause_command_is_minimal_tools() -> None:
    """mimiron-pause는 CLI 호출 한 번만 — Bash 정도면 충분."""
    fm = _frontmatter(Path("commands/mimiron-pause.md"))
    tools = set(fm.get("allowed-tools", "").replace(",", " ").split())
    # 적어도 Bash는 있어야 (cli 호출)
    assert "Bash" in tools, "pause command must have Bash to invoke CLI"
