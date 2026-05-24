#!/usr/bin/env python3
"""PostToolUse hook for Write/Edit/MultiEdit/NotebookEdit — owned_files drift 감지.

Hard reject 모드: drift 감지 시 ``permissionDecision: deny`` 출력으로 commit 차단.
드리프트 튜플은 항상 ``drift.log`` 에 기록(감사 추적)되고, 그 뒤 두 가지 이스케이프 경로가 있다:

- ``.mimiron/`` 하위 sidecar 경로(rel_path 가 ``.mimiron`` 이거나 ``.mimiron/`` 로 시작): reject 우회.
- 해당 슬러그 ``state.spec_unlocked == true``: 그 슬러그의 튜플만 reject 우회.

모든 드리프트 튜플이 이스케이프되면 ``additionalContext`` warn 으로만 통과. 한 튜플이라도
실제 reject 후보면 ``permissionDecision: deny`` 응답을 낸다.
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
        raw = json.load(sys.stdin)
    except json.JSONDecodeError:
        return {}
    return raw if isinstance(raw, dict) else {}


def collect_owned_files(plan_yaml_path: Path) -> set[str]:
    """plan.yaml의 모든 task.owned_files의 합집합."""
    try:
        # Make mimiron.yaml_compat importable from the plugin tree.
        # Hooks are launched as standalone Python processes, not as part of
        # the mimiron package — so we extend sys.path before the lazy import.
        plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT") or str(
            Path(__file__).resolve().parent.parent
        )
        src_path = f"{plugin_root}/src"
        if src_path not in sys.path:
            sys.path.insert(0, src_path)
        from mimiron.yaml_compat import safe_load
        raw = safe_load(plan_yaml_path.read_text(encoding="utf-8")) or {}
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


def is_mimiron_sidecar(rel_path: str) -> bool:
    """``.mimiron`` 자체 또는 ``.mimiron/`` 하위 경로면 True (POSIX prefix check)."""
    return rel_path == ".mimiron" or rel_path.startswith(".mimiron/")


def is_slug_spec_unlocked(mimiron_dir: Path, slug: str) -> bool:
    """``<mimiron_dir>/<slug>/state.json`` 의 ``spec_unlocked`` 플래그.

    파일 없음/JSON 파싱 실패/키 누락 모두 False 로 안전하게 떨어진다.
    """
    state_path = mimiron_dir / slug / "state.json"
    try:
        raw = json.loads(state_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return False
    return bool(raw.get("spec_unlocked", False))


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
    mimiron_dir = project / ".mimiron"
    drifts = detect_drift(
        mimiron_dir=mimiron_dir,
        cwd=project,
        edited_abs_path=edited,
    )
    if not drifts:
        return 0
    # 감사 추적: 모든 드리프트 튜플을 drift.log 에 적재 (whitelist/escape 와 무관).
    for slug, rel in drifts:
        append_drift_log(mimiron_dir, slug, rel)
    # Reject 후보: sidecar 경로가 아니면서 슬러그가 spec_unlocked 도 아닌 튜플.
    reject_candidates = [
        (slug, rel)
        for slug, rel in drifts
        if not is_mimiron_sidecar(rel) and not is_slug_spec_unlocked(mimiron_dir, slug)
    ]
    first_slug, first_rel = drifts[0]
    if reject_candidates:
        rslug, rrel = reject_candidates[0]
        reason = (
            f"Mimiron drift reject: '{rrel}' 는 슬러그 '{rslug}' 의 owned_files 에 "
            f"속하지 않습니다 (phase=execute). 해결책: (a) plan.yaml 의 task "
            f"owned_files 에 추가, (b) `state.spec_unlocked=true` 로 박기, "
            f"(c) 편집 의도가 mimiron 범위 밖이면 다른 디렉토리로 이동."
        )
        output: dict[str, object] = {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }
    else:
        # 모든 드리프트가 whitelisted/escaped — warn additionalContext 만 출력.
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": (
                    f"⚠ Mimiron drift (whitelisted/escaped): {first_rel!r} for "
                    f"slug {first_slug!r}. Logged to drift.log."
                ),
            }
        }
    print(json.dumps(output, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
