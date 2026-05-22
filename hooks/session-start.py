#!/usr/bin/env python3
"""SessionStart hook — 진행 중 Mimiron 슬러그 컨텍스트 주입.

Claude Code의 SessionStart event는 stdin 없이도 발동. 본 hook은 cwd/.mimiron/
을 스캔해 phase ∉ {done, stuck, paused} 슬러그가 있으면 additionalContext로
요약을 주입한다. Mimiron 안 쓰는 프로젝트면 *조용히 종료*.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


HIDDEN_PHASES = frozenset({"done", "stuck", "paused"})


def _project_root() -> Path:
    """Claude Code가 주입하는 CLAUDE_PROJECT_DIR 우선, 미설정 시 cwd."""
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    return Path(env) if env else Path.cwd()


def collect_in_progress(mimiron_dir: Path) -> list[dict[str, object]]:
    """phase ∉ HIDDEN_PHASES + paused=False 인 슬러그 목록."""
    out: list[dict[str, object]] = []
    if not mimiron_dir.exists():
        return out
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
        phase = state.get("phase")
        if phase in HIDDEN_PHASES or state.get("paused", False):
            continue
        out.append(
            {
                "slug": state.get("slug", slug_dir.name),
                "phase": phase,
                "persistent": bool(state.get("persistent", False)),
            }
        )
    return out


def render_context(in_progress: list[dict[str, object]]) -> str:
    lines = ["## Mimiron in-progress slugs"]
    for s in in_progress:
        persist = "persistent" if s["persistent"] else "manual"
        lines.append(f"- `{s['slug']}` — phase={s['phase']} ({persist})")
    lines.append("")
    lines.append(
        "Run `mimiron status <slug>` for details, "
        "or `/mimiron resume <slug>` to continue."
    )
    return "\n".join(lines)


def main() -> int:
    in_progress = collect_in_progress(_project_root() / ".mimiron")
    if not in_progress:
        return 0
    output = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": render_context(in_progress),
        }
    }
    print(json.dumps(output, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
