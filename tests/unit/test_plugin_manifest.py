"""Mimiron plugin layout sanity — auto-discovery 기반.

.claude-plugin/plugin.json은 components를 *명시* 안 한다 (Claude Code는
폴더 기반 auto-discovery). 본 테스트는:
1. plugin.json의 필수 필드(name, description)가 존재
2. 디렉토리 구조가 spec § 4.1의 약속과 일치 (skills/, agents/, commands/, hooks/)
3. hooks/hooks.json이 가리키는 스크립트가 실제로 존재
"""
import json
from pathlib import Path


ROOT = Path(__file__).parent.parent.parent
PLUGIN_JSON = ROOT / ".claude-plugin" / "plugin.json"
HOOKS_JSON = ROOT / "hooks" / "hooks.json"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_plugin_json_has_required_fields() -> None:
    raw = _load_json(PLUGIN_JSON)
    assert raw.get("name") == "mimiron"
    assert isinstance(raw.get("description"), str)
    assert len(raw["description"]) > 30


def test_skills_directory_has_at_least_phase_skills() -> None:
    """spec § 4.1: clarify/spec/plan/execute/evaluate/finalize/unstuck *최소*."""
    skills_dir = ROOT / "skills"
    expected = {"clarify", "spec", "plan", "execute", "evaluate", "finalize", "unstuck"}
    present = {p.name for p in skills_dir.iterdir() if p.is_dir() and (p / "SKILL.md").exists()}
    missing = expected - present
    assert not missing, f"missing skills (each needs SKILL.md): {missing}"


def test_agents_directory_has_three_tiers() -> None:
    """spec § 4.4: mimiron-worker / mimiron-tester / mimiron-reviewer."""
    agents_dir = ROOT / "agents"
    expected = {"mimiron-worker.md", "mimiron-tester.md", "mimiron-reviewer.md"}
    present = {p.name for p in agents_dir.glob("*.md")}
    missing = expected - present
    assert not missing, f"missing agent files: {missing}"


def test_commands_directory_has_entrypoints() -> None:
    """spec § 4.1: 5 thin wrappers."""
    commands_dir = ROOT / "commands"
    expected = {
        "mimiron.md",
        "mimiron-resume.md",
        "mimiron-status.md",
        "mimiron-pause.md",
        "mimiron-unstuck.md",
    }
    present = {p.name for p in commands_dir.glob("*.md")}
    missing = expected - present
    assert not missing, f"missing command wrappers: {missing}"


def test_hooks_config_scripts_exist() -> None:
    """hooks.json이 가리키는 .py 파일이 실제로 존재."""
    config = _load_json(HOOKS_JSON)
    hooks_by_event = config.get("hooks", {})
    for event_name, entries in hooks_by_event.items():
        for entry in entries:
            for hook_def in entry.get("hooks", []):
                cmd = hook_def.get("command", "")
                # ${CLAUDE_PROJECT_DIR}/hooks/<name>.py 형식
                if "${CLAUDE_PROJECT_DIR}/hooks/" in cmd:
                    script = cmd.split("${CLAUDE_PROJECT_DIR}/hooks/", 1)[1]
                    script_path = ROOT / "hooks" / script
                    assert script_path.exists(), (
                        f"hooks.json references missing script: {event_name}/{script}"
                    )


def test_benchmarks_at_least_three() -> None:
    """spec § 7.5: suite 신호 다양성 — 최소 3개."""
    bench_dir = ROOT / "benchmarks"
    present = [p for p in bench_dir.iterdir() if p.is_dir() and (p / "benchmark.yaml").exists()]
    assert len(present) >= 3, f"need ≥3 benchmarks, got {len(present)}: {[p.name for p in present]}"


def test_evals_fixtures_present() -> None:
    """evals/ — mechanical gate fixture 모음."""
    evals_dir = ROOT / "evals"
    assert evals_dir.exists()
    fixtures = list(evals_dir.glob("*.toml"))
    assert fixtures, "evals/ must have at least one .toml fixture"
