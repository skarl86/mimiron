"""hooks/ 단위 테스트 — Python import 후 함수 호출.

hooks는 stdin/stdout JSON으로 외부 invocation을 받지만, 로직은 *함수형*
으로 분리돼 있어 in-process 테스트 가능.
"""
from __future__ import annotations

import importlib.util
import io
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


HOOKS_DIR = Path(__file__).parent.parent.parent / "hooks"


def _import_hook(name: str, file_basename: str) -> object:
    """hooks/<file>.py를 모듈로 import (hyphen 파일명 대응)."""
    path = HOOKS_DIR / file_basename
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def session_start():
    return _import_hook("mimiron_hook_session_start", "session-start.py")


@pytest.fixture
def stop_hook():
    return _import_hook("mimiron_hook_stop", "stop-hook.py")


@pytest.fixture
def post_toolwrite():
    return _import_hook("mimiron_hook_post_toolwrite", "post-toolwrite.py")


# ───────────────────────── session-start ─────────────────────────


def test_session_start_empty_mimiron_returns_no_slugs(tmp_path: Path, session_start) -> None:
    out = session_start.collect_in_progress(tmp_path / ".mimiron")
    assert out == []


def test_session_start_skips_done_stuck_paused(tmp_path: Path, session_start) -> None:
    md = tmp_path / ".mimiron"
    for phase in ("done", "stuck", "paused"):
        s = md / phase
        s.mkdir(parents=True)
        (s / "state.json").write_text(
            json.dumps({"schema_version": 1, "slug": phase, "phase": phase, "persistent": True})
        )
    out = session_start.collect_in_progress(md)
    assert out == []


def test_session_start_includes_in_progress_slugs(tmp_path: Path, session_start) -> None:
    md = tmp_path / ".mimiron"
    s = md / "demo"
    s.mkdir(parents=True)
    (s / "state.json").write_text(
        json.dumps({"schema_version": 1, "slug": "demo", "phase": "execute", "persistent": True})
    )
    out = session_start.collect_in_progress(md)
    assert len(out) == 1
    assert out[0]["slug"] == "demo"
    assert out[0]["phase"] == "execute"
    assert out[0]["persistent"] is True


def test_session_start_skips_paused_flag(tmp_path: Path, session_start) -> None:
    """phase는 진행 중이어도 paused=True면 제외."""
    md = tmp_path / ".mimiron"
    s = md / "demo"
    s.mkdir(parents=True)
    (s / "state.json").write_text(
        json.dumps(
            {
                "schema_version": 1, "slug": "demo", "phase": "execute",
                "persistent": True, "paused": True,
            }
        )
    )
    assert session_start.collect_in_progress(md) == []


# ───────────────────────── stop-hook ─────────────────────────


def _now_minus(seconds: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()


def test_stop_hook_non_persistent_is_skip(stop_hook) -> None:
    state = {"persistent": False, "phase": "execute"}
    verdict = stop_hook.evaluate_slug(state, wall_clock_max_s=14400, token_budget=500_000)
    assert verdict == "skip"


def test_stop_hook_done_phase_is_skip(stop_hook) -> None:
    state = {"persistent": True, "phase": "done"}
    verdict = stop_hook.evaluate_slug(state, wall_clock_max_s=14400, token_budget=500_000)
    assert verdict == "skip"


def test_stop_hook_paused_flag_is_skip(stop_hook) -> None:
    state = {"persistent": True, "phase": "execute", "paused": True}
    verdict = stop_hook.evaluate_slug(state, wall_clock_max_s=14400, token_budget=500_000)
    assert verdict == "skip"


def test_stop_hook_eligible_slug_returns_resume(stop_hook) -> None:
    state = {
        "persistent": True, "phase": "execute", "paused": False,
        "wall_clock_started_at": _now_minus(60), "token_usage": 100,
    }
    verdict = stop_hook.evaluate_slug(state, wall_clock_max_s=14400, token_budget=500_000)
    assert verdict == "resume"


def test_stop_hook_wall_clock_exceeded_returns_pause(stop_hook) -> None:
    state = {
        "persistent": True, "phase": "execute",
        "wall_clock_started_at": _now_minus(20000),  # 5h+
        "token_usage": 100,
    }
    verdict = stop_hook.evaluate_slug(state, wall_clock_max_s=14400, token_budget=500_000)
    assert verdict == "pause"


def test_stop_hook_token_budget_exceeded_returns_pause(stop_hook) -> None:
    state = {
        "persistent": True, "phase": "execute",
        "wall_clock_started_at": _now_minus(60),
        "token_usage": 600_000,
    }
    verdict = stop_hook.evaluate_slug(state, wall_clock_max_s=14400, token_budget=500_000)
    assert verdict == "pause"


def test_stop_hook_find_target_marks_pause_slugs(tmp_path: Path, stop_hook) -> None:
    """cap 초과 슬러그는 paused=True로 마킹된 후 resume 후보에서 제외."""
    md = tmp_path / ".mimiron"
    # 초과 슬러그
    over = md / "over"
    over.mkdir(parents=True)
    (over / "state.json").write_text(
        json.dumps(
            {
                "schema_version": 1, "slug": "over", "phase": "execute",
                "persistent": True, "paused": False,
                "wall_clock_started_at": _now_minus(20000), "token_usage": 100,
            }
        )
    )
    target = stop_hook.find_resume_target(md)
    assert target is None
    after = json.loads((over / "state.json").read_text())
    assert after["paused"] is True


# ───────────────────────── post-toolwrite ─────────────────────────


def _seed_execute_plan(md: Path, slug: str, owned_files: list[str]) -> None:
    s = md / slug
    s.mkdir(parents=True, exist_ok=True)
    (s / "state.json").write_text(
        json.dumps({"schema_version": 1, "slug": slug, "phase": "execute"})
    )
    (s / "plan.yaml").write_text(
        "schema_version: 1\nslug: {slug}\nspec_hash: x\ntasks:\n".format(slug=slug)
        + "".join(
            f"  - id: T0{i}\n    title: t\n    owned_files: [{f!r}]\n    "
            f"expected_artifacts: [{f!r}]\n"
            for i, f in enumerate(owned_files, start=1)
        )
    )


def test_post_toolwrite_no_drift_when_file_in_owned(
    tmp_path: Path, post_toolwrite, monkeypatch: pytest.MonkeyPatch
) -> None:
    md = tmp_path / ".mimiron"
    _seed_execute_plan(md, "demo", ["a.py"])
    monkeypatch.chdir(tmp_path)
    drifts = post_toolwrite.detect_drift(
        mimiron_dir=md,
        cwd=tmp_path,
        edited_abs_path=tmp_path / "a.py",
    )
    assert drifts == []


def test_post_toolwrite_drift_detected_when_file_not_owned(
    tmp_path: Path, post_toolwrite, monkeypatch: pytest.MonkeyPatch
) -> None:
    md = tmp_path / ".mimiron"
    _seed_execute_plan(md, "demo", ["a.py"])
    monkeypatch.chdir(tmp_path)
    drifts = post_toolwrite.detect_drift(
        mimiron_dir=md,
        cwd=tmp_path,
        edited_abs_path=tmp_path / "secret.py",
    )
    assert len(drifts) == 1
    assert drifts[0] == ("demo", "secret.py")


def test_post_toolwrite_no_drift_when_phase_not_execute(
    tmp_path: Path, post_toolwrite, monkeypatch: pytest.MonkeyPatch
) -> None:
    md = tmp_path / ".mimiron"
    _seed_execute_plan(md, "demo", ["a.py"])
    # phase 변경
    state = md / "demo" / "state.json"
    raw = json.loads(state.read_text())
    raw["phase"] = "plan"
    state.write_text(json.dumps(raw))
    monkeypatch.chdir(tmp_path)
    drifts = post_toolwrite.detect_drift(
        mimiron_dir=md, cwd=tmp_path, edited_abs_path=tmp_path / "secret.py",
    )
    assert drifts == []


def test_post_toolwrite_append_drift_log(tmp_path: Path, post_toolwrite) -> None:
    md = tmp_path / ".mimiron"
    (md / "demo").mkdir(parents=True)
    post_toolwrite.append_drift_log(md, "demo", "secret.py")
    log = md / "demo" / "drift.log"
    assert log.exists()
    content = log.read_text()
    assert "file=secret.py" in content


def test_post_toolwrite_outside_cwd_is_ignored(
    tmp_path: Path, post_toolwrite, monkeypatch: pytest.MonkeyPatch
) -> None:
    md = tmp_path / ".mimiron"
    _seed_execute_plan(md, "demo", ["a.py"])
    monkeypatch.chdir(tmp_path)
    # /tmp 처럼 cwd 밖
    drifts = post_toolwrite.detect_drift(
        mimiron_dir=md, cwd=tmp_path, edited_abs_path=Path("/etc/passwd"),
    )
    assert drifts == []


# ─────── CLAUDE_PROJECT_DIR env var routing (defect-fix from session 7ee14442) ───────


def test_session_start_uses_claude_project_dir_env(
    tmp_path: Path, session_start, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Claude Code가 hook 실행 시 cwd가 어디든, CLAUDE_PROJECT_DIR이 정답."""
    md = tmp_path / ".mimiron"
    s = md / "demo"
    s.mkdir(parents=True)
    (s / "state.json").write_text(
        json.dumps({"schema_version": 1, "slug": "demo", "phase": "execute", "persistent": True})
    )
    # chdir을 *다른 곳*으로 (Claude Code가 user의 home에서 실행하는 케이스 시뮬레이션)
    other_dir = tmp_path.parent / "totally-unrelated-cwd"
    other_dir.mkdir(exist_ok=True)
    monkeypatch.chdir(other_dir)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    # _project_root()이 env var를 우선해야
    assert session_start._project_root() == tmp_path


def test_stop_hook_uses_claude_project_dir_env(
    tmp_path: Path, stop_hook, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path.parent)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    assert stop_hook._project_root() == tmp_path


def test_post_toolwrite_uses_claude_project_dir_env(
    tmp_path: Path, post_toolwrite, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path.parent)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    assert post_toolwrite._project_root() == tmp_path


def test_project_root_falls_back_to_cwd_when_env_missing(
    tmp_path: Path, session_start, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    assert session_start._project_root() == tmp_path


# ─────── post-toolwrite hard-reject (T02 / drift-hook-hard-reject) ───────


def _seed_execute_slug_with_unlock(
    md: Path, slug: str, owned_files: list[str], *, spec_unlocked: bool
) -> None:
    """T02 헬퍼: state.spec_unlocked 플래그까지 명시적으로 직렬화한 슬러그 시드."""
    s = md / slug
    s.mkdir(parents=True, exist_ok=True)
    (s / "state.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "slug": slug,
                "phase": "execute",
                "spec_unlocked": spec_unlocked,
            }
        )
    )
    (s / "plan.yaml").write_text(
        "schema_version: 1\nslug: {slug}\nspec_hash: x\ntasks:\n".format(slug=slug)
        + "".join(
            f"  - id: T0{i}\n    title: t\n    owned_files: [{f!r}]\n    "
            f"expected_artifacts: [{f!r}]\n"
            for i, f in enumerate(owned_files, start=1)
        )
    )


def _run_main_with_event(
    post_toolwrite, monkeypatch: pytest.MonkeyPatch, event: dict
) -> int:
    """stdin 을 JSON event 로 채우고 main() 호출."""
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))
    return post_toolwrite.main()


def test_post_toolwrite_main_emits_deny_on_drift(
    tmp_path: Path,
    post_toolwrite,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC01: drift + sidecar 아님 + spec_unlocked=False → permissionDecision=deny."""
    md = tmp_path / ".mimiron"
    _seed_execute_slug_with_unlock(md, "demo", ["some_owned.py"], spec_unlocked=False)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    event = {
        "tool_name": "Write",
        "tool_input": {"file_path": str(tmp_path / "another.py")},
    }
    rc = _run_main_with_event(post_toolwrite, monkeypatch, event)
    assert rc == 0
    captured = capsys.readouterr()
    out = json.loads(captured.out)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    # drift.log 가 한 줄 이상 적재돼야 (감사 추적은 reject 와 무관)
    drift_log = md / "demo" / "drift.log"
    assert drift_log.exists()
    assert "file=another.py" in drift_log.read_text(encoding="utf-8")


def test_post_toolwrite_main_skips_deny_when_spec_unlocked(
    tmp_path: Path,
    post_toolwrite,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC02: state.spec_unlocked=True 슬러그는 deny 건너뛰고 additionalContext warn 만."""
    md = tmp_path / ".mimiron"
    _seed_execute_slug_with_unlock(md, "demo", ["some_owned.py"], spec_unlocked=True)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    event = {
        "tool_name": "Write",
        "tool_input": {"file_path": str(tmp_path / "another.py")},
    }
    rc = _run_main_with_event(post_toolwrite, monkeypatch, event)
    assert rc == 0
    captured = capsys.readouterr()
    out = json.loads(captured.out)
    hook_out = out["hookSpecificOutput"]
    assert "permissionDecision" not in hook_out
    assert "additionalContext" in hook_out
    # 감사 추적: drift.log 는 무조건 적재
    drift_log = md / "demo" / "drift.log"
    assert drift_log.exists()
    assert "file=another.py" in drift_log.read_text(encoding="utf-8")


def test_post_toolwrite_main_skips_deny_for_mimiron_sidecar_paths(
    tmp_path: Path,
    post_toolwrite,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC03: .mimiron/ 하위 sidecar 편집은 spec_unlocked=False 여도 deny 우회."""
    md = tmp_path / ".mimiron"
    _seed_execute_slug_with_unlock(md, "demo", ["some_owned.py"], spec_unlocked=False)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    sidecar = tmp_path / ".mimiron" / "demo" / "evaluation" / "semantic.md"
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "tool_name": "Write",
        "tool_input": {"file_path": str(sidecar)},
    }
    rc = _run_main_with_event(post_toolwrite, monkeypatch, event)
    assert rc == 0
    captured = capsys.readouterr()
    out = json.loads(captured.out)
    hook_out = out["hookSpecificOutput"]
    assert "permissionDecision" not in hook_out
    assert "additionalContext" in hook_out
    drift_log = md / "demo" / "drift.log"
    assert drift_log.exists()
    assert ".mimiron/demo/evaluation/semantic.md" in drift_log.read_text(encoding="utf-8")


def test_post_toolwrite_main_emits_deny_for_real_source_drift(
    tmp_path: Path,
    post_toolwrite,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC04: deny 응답 reason 에 'Mimiron drift reject' 리터럴, 슬러그명, rel path 포함."""
    md = tmp_path / ".mimiron"
    _seed_execute_slug_with_unlock(md, "demo", ["some_owned.py"], spec_unlocked=False)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    event = {
        "tool_name": "Write",
        "tool_input": {"file_path": str(tmp_path / "another.py")},
    }
    rc = _run_main_with_event(post_toolwrite, monkeypatch, event)
    assert rc == 0
    captured = capsys.readouterr()
    out = json.loads(captured.out)
    hook_out = out["hookSpecificOutput"]
    assert hook_out["permissionDecision"] == "deny"
    reason = hook_out["permissionDecisionReason"]
    assert "Mimiron drift reject" in reason
    assert "demo" in reason
    assert "another.py" in reason


def test_post_toolwrite_drift_log_appended_even_when_whitelisted(
    tmp_path: Path,
    post_toolwrite,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC05: sidecar 편집(whitelist) 도 drift.log 는 반드시 한 줄 이상 적재."""
    md = tmp_path / ".mimiron"
    _seed_execute_slug_with_unlock(md, "demo", ["some_owned.py"], spec_unlocked=False)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    sidecar = tmp_path / ".mimiron" / "demo" / "foo.md"
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "tool_name": "Write",
        "tool_input": {"file_path": str(sidecar)},
    }
    rc = _run_main_with_event(post_toolwrite, monkeypatch, event)
    assert rc == 0
    captured = capsys.readouterr()
    out = json.loads(captured.out)
    # reject 우회 확인
    assert "permissionDecision" not in out["hookSpecificOutput"]
    # drift.log 적재 확인
    drift_log = md / "demo" / "drift.log"
    assert drift_log.exists()
    log_text = drift_log.read_text(encoding="utf-8")
    assert ".mimiron/demo/foo.md" in log_text
    # 최소 한 줄 이상
    assert len([ln for ln in log_text.splitlines() if ln.strip()]) >= 1
