"""Regression guard: every user-facing skill / agent / command file MUST contain
a `user_language` directive so that the language preference persists across all
phases of the Mimiron pipeline.

If you add a new skill or agent that talks to the user, this test will fail
until you add the standard directive. That's the point — drift is detected at
test time, not at runtime when a user notices English replies in a Korean run.
"""
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parent.parent.parent


# Files that produce *user-facing* natural-language output. Each MUST mention
# `user_language` so the language preference threads through the pipeline.
USER_FACING_FILES = [
    REPO / "skills/clarify/SKILL.md",
    REPO / "skills/spec/SKILL.md",
    REPO / "skills/plan/SKILL.md",
    REPO / "skills/execute/SKILL.md",
    REPO / "skills/evaluate/SKILL.md",
    REPO / "skills/finalize/SKILL.md",
    REPO / "skills/unstuck/SKILL.md",
    REPO / "skills/bench-judge/SKILL.md",
    REPO / "agents/mimiron-worker.md",
    REPO / "agents/mimiron-tester.md",
    REPO / "agents/mimiron-reviewer.md",
    REPO / "commands/mimiron.md",
]


@pytest.mark.parametrize("path", USER_FACING_FILES, ids=lambda p: p.relative_to(REPO).as_posix())
def test_file_mentions_user_language(path: Path) -> None:
    assert path.exists(), f"missing: {path}"
    text = path.read_text(encoding="utf-8")
    assert "user_language" in text, (
        f"{path.relative_to(REPO)} is user-facing but lacks a `user_language` directive. "
        "Add a short section explaining how it reads state.user_language and what to do "
        "when it is null. See skills/clarify/SKILL.md for the canonical wording."
    )


def test_mimiron_command_passes_language_flag_to_init() -> None:
    """The /mimiron command must forward the language choice to `mimiron init`,
    otherwise state.user_language stays null and the directive is dead."""
    text = (REPO / "commands/mimiron.md").read_text(encoding="utf-8")
    assert "--language" in text, (
        "commands/mimiron.md must instruct Claude to pass --language to `mimiron init`. "
        "Without that, user_language never lands in state.json."
    )
    assert "AskUserQuestion" in text, (
        "commands/mimiron.md must use AskUserQuestion to confirm the language choice "
        "(per the agreed design: explicit selection is the most robust path)."
    )


def test_director_skill_propagates_language_to_workers() -> None:
    """execute skill dispatches workers via Task. Workers don't read state.json
    themselves — they receive `user_language` in the dispatch prompt. That contract
    must be documented in the execute skill."""
    text = (REPO / "skills/execute/SKILL.md").read_text(encoding="utf-8")
    # The execute directive should mention propagating to dispatched agents.
    assert "user_language" in text
    assert "dispatch" in text.lower() or "agent" in text.lower(), (
        "execute skill must document that it propagates user_language to dispatched "
        "agents (worker/tester) via the Task prompt — workers read it from the prompt, "
        "not from state.json."
    )
