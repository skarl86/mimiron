#!/usr/bin/env python3
"""PostToolUse hook for Write/Edit/MultiEdit/NotebookEdit — owned_files drift 감지.

v0: warn + drift.log에 append. v1+: reject (decision="block" with rejection reason).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


WATCHED_TOOLS = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit"})


def _project_root() -> Path:
    """Claude Code가 주입하는 CLAUDE_PROJECT_DIR 우선, 미설정 시 cwd."""
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    return Path(env) if env else Path.cwd()


def _read_event() -> dict[str, object]:
    try:
        return json.load(sys.stdin)
    except json.JSONDecodeError:
        return {}


def collect_owned_files(plan_yaml_path: Path) -> set[str]:
    """plan.yaml의 모든 task.owned_files의 합집합."""
    try:
        import yaml
        raw = yaml.safe_load(plan_yaml_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return set()
    owned: set[str] = set()
    for t in raw.get("tasks", []) or []:
        for f in t.get("owned_files", []) or []:
            if isinstance(f, str):
                owned.add(f)
    return owned


def detect_drift(
    *,
    mimiron_dir: Path,
    cwd: Path,
    edited_abs_path: Path,
) -> list[tuple[str, str]]:
    """(slug, relative_path) 페어 목록 — phase=execute 슬러그 중 owned 밖이면.

    cwd 밖 파일은 무시 (Mimiron 도메인 밖). 다른 phase면 검사 안 함.
    """
    drifts: list[tuple[str, str]] = []
    try:
        rel = str(edited_abs_path.resolve().relative_to(cwd))
    except ValueError:
        return drifts
    if not mimiron_dir.exists():
        return drifts
    for slug_dir in sorted(mimiron_dir.iterdir()):
        if not slug_dir.is_dir() or slug_dir.name == "_global":
            continue
        state_path = slug_dir / "state.json"
        plan_path = slug_dir / "plan.yaml"
        if not state_path.exists() or not plan_path.exists():
            continue
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if state.get("phase") != "execute":
            continue
        owned = collect_owned_files(plan_path)
        if not owned:
            continue
        if rel not in owned:
            drifts.append((state.get("slug", slug_dir.name), rel))
    return drifts


def append_drift_log(mimiron_dir: Path, slug: str, rel_path: str) -> None:
    log = mimiron_dir / slug / "drift.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat()
    line = f"{ts}\tfile={rel_path}\n"
    with log.open("a", encoding="utf-8") as f:
        f.write(line)


def main() -> int:
    event = _read_event()
    if event.get("tool_name") not in WATCHED_TOOLS:
        return 0
    tool_input = event.get("tool_input") or {}
    raw_path = tool_input.get("file_path") if isinstance(tool_input, dict) else None
    if not raw_path or not isinstance(raw_path, str):
        return 0
    project = _project_root()
    edited = Path(raw_path)
    if not edited.is_absolute():
        edited = project / edited
    drifts = detect_drift(
        mimiron_dir=project / ".mimiron",
        cwd=project,
        edited_abs_path=edited,
    )
    if not drifts:
        return 0
    for slug, rel in drifts:
        append_drift_log(project / ".mimiron", slug, rel)
    # v0: warn-only — additionalContext로 알리고 작업은 통과시킴
    first_slug, first_rel = drifts[0]
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": (
                f"⚠ Mimiron drift: {first_rel!r} is not in any owned_files of "
                f"slug {first_slug!r} (phase=execute). Logged to drift.log. "
                "v0 warn-only, v1+ will reject."
            ),
        }
    }
    print(json.dumps(output, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
