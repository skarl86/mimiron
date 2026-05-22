#!/usr/bin/env python3
"""Stop hook — persistent slug 재투입 (spec § 5.4).

persistent=true && phase ∉ {done, stuck, paused} && paused=false &&
wall_clock/token cap 미초과 → decision="block" + reason 으로 Claude를
다시 working state로 둠 (Stop event abort). cap 초과 시 state.paused=true.

이 hook은 Mimiron 안 쓰는 프로젝트에서 *완전히 무해*해야 함 (.mimiron/
없으면 즉시 exit 0, additionalContext 발행도 없음).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def _project_root() -> Path:
    """Claude Code가 주입하는 CLAUDE_PROJECT_DIR 우선, 미설정 시 cwd."""
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    return Path(env) if env else Path.cwd()


HIDDEN_PHASES = frozenset({"done", "stuck", "paused"})
WALL_CLOCK_DEFAULT_S = 14400  # 4h
TOKEN_BUDGET_DEFAULT = 500_000


def _parse_iso(s: object) -> datetime | None:
    if not isinstance(s, str):
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _load_thresholds(mimiron_dir: Path) -> tuple[int, int]:
    """(wall_clock_max_s, token_budget) — 파싱 실패 시 default."""
    path = mimiron_dir / "_global" / "thresholds.yaml"
    if not path.exists():
        return WALL_CLOCK_DEFAULT_S, TOKEN_BUDGET_DEFAULT
    try:
        import yaml
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return WALL_CLOCK_DEFAULT_S, TOKEN_BUDGET_DEFAULT
    return (
        int(raw.get("wall_clock_max_s", WALL_CLOCK_DEFAULT_S)),
        int(raw.get("token_budget", TOKEN_BUDGET_DEFAULT)),
    )


def evaluate_slug(
    state: dict[str, object],
    *,
    wall_clock_max_s: int,
    token_budget: int,
    now: datetime | None = None,
) -> str:
    """반환:
    - "resume"  → 이 슬러그를 이어서 작업해야 함
    - "pause"   → cap 초과 → state.paused=true 마킹 후 skip
    - "skip"    → 대상 아님 (persistent=false, phase=done 등)
    """
    if not state.get("persistent", False):
        return "skip"
    phase = state.get("phase")
    if phase in HIDDEN_PHASES or state.get("paused", False):
        return "skip"
    started = _parse_iso(state.get("wall_clock_started_at"))
    if started is not None:
        now_ts = now or datetime.now(timezone.utc)
        elapsed = (now_ts - started).total_seconds()
        if elapsed > wall_clock_max_s:
            return "pause"
    if int(state.get("token_usage", 0) or 0) > token_budget:
        return "pause"
    return "resume"


def find_resume_target(mimiron_dir: Path) -> tuple[str, str] | None:
    """첫 resume 후보를 (slug, phase)로 반환. 없으면 None.

    이 함수는 *side effect를 가질 수 있음* — cap 초과 슬러그를 paused로 마킹.
    """
    if not mimiron_dir.exists():
        return None
    wall_clock_max_s, token_budget = _load_thresholds(mimiron_dir)
    for slug_dir in sorted(mimiron_dir.iterdir()):
        if not slug_dir.is_dir() or slug_dir.name == "_global":
            continue
        state_path = slug_dir / "state.json"
        if not state_path.exists():
            continue
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        verdict = evaluate_slug(
            state,
            wall_clock_max_s=wall_clock_max_s,
            token_budget=token_budget,
        )
        if verdict == "skip":
            continue
        if verdict == "pause":
            state["paused"] = True
            state_path.write_text(
                json.dumps(state, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            continue
        # resume
        return state.get("slug", slug_dir.name), state.get("phase", "?")
    return None


def main() -> int:
    target = find_resume_target(_project_root() / ".mimiron")
    if target is None:
        return 0
    slug, phase = target
    output = {
        "decision": "block",
        "reason": (
            f"Mimiron persistent slug {slug!r} in phase={phase}. "
            f"Continue with `/mimiron resume {slug}`."
        ),
    }
    print(json.dumps(output, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
