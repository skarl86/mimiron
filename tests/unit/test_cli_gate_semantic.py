"""mimiron gate <slug> semantic — evaluate skill이 작성한 semantic.json을
읽어 verdict.json 합산 + state 전이.
"""
import json
from pathlib import Path
import pytest
from mimiron.cli import main
from mimiron.state import State


def _seed_evaluate_phase(tmp_project: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """init + state.phase=evaluate로 강제. semantic gate 테스트의 prelude."""
    monkeypatch.chdir(tmp_project)
    main(["init", "demo"])
    sidecar = tmp_project / ".mimiron" / "demo"
    state = State.load(sidecar / "state.json")
    state.phase = "evaluate"
    state.save(sidecar / "state.json")
    return sidecar


def _write_semantic(sidecar: Path, *, verdict: str, score: float, samples: list[float] | None = None) -> None:
    """semantic.json 작성 — evaluate skill의 산출을 흉내."""
    (sidecar / "evaluation").mkdir(parents=True, exist_ok=True)
    (sidecar / "evaluation" / "semantic.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "slug": "demo",
                "phase": "evaluate",
                "kind": "semantic",
                "verdict": verdict,
                "score": score,
                "samples": samples or [score, score, score],
                "details": {"ac_results": [], "rationale": "test stub"},
                "ts": "2026-05-23T00:00:00+00:00",
            }
        )
    )


def test_semantic_gate_missing_file_exits_runtime_error(
    tmp_project: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed_evaluate_phase(tmp_project, monkeypatch)
    rc = main(["gate", "demo", "semantic"])
    assert rc != 0
    err = capsys.readouterr().err
    assert "semantic.json" in err


def test_semantic_gate_pass_transitions_to_finalize(
    tmp_project: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sidecar = _seed_evaluate_phase(tmp_project, monkeypatch)
    _write_semantic(sidecar, verdict="pass", score=0.88)
    capsys.readouterr()
    rc = main(["gate", "demo", "semantic"])
    assert rc == 0
    state = State.load(sidecar / "state.json")
    assert state.phase == "finalize"
    assert state.consecutive_gate_fails == 0
    assert len(state.gate_history) == 1
    assert state.gate_history[0].kind == "semantic"
    assert state.gate_history[0].verdict == "pass"
    # verdict.json (per-gate) 작성됐어야
    assert (sidecar / "evaluation" / "semantic.json").exists()


def test_semantic_gate_fail_keeps_evaluate_phase_and_bumps_consec(
    tmp_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sidecar = _seed_evaluate_phase(tmp_project, monkeypatch)
    _write_semantic(sidecar, verdict="fail", score=0.40)
    rc = main(["gate", "demo", "semantic"])
    assert rc != 0
    state = State.load(sidecar / "state.json")
    assert state.phase == "evaluate"
    assert state.consecutive_gate_fails == 1


def test_semantic_gate_needs_review_sets_paused(
    tmp_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sidecar = _seed_evaluate_phase(tmp_project, monkeypatch)
    _write_semantic(sidecar, verdict="needs_review", score=0.78)
    rc = main(["gate", "demo", "semantic"])
    assert rc == 0  # needs_review는 fail 아님
    state = State.load(sidecar / "state.json")
    assert state.paused is True
    assert state.phase == "evaluate"


def test_semantic_gate_third_consecutive_fail_marks_stuck(
    tmp_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sidecar = _seed_evaluate_phase(tmp_project, monkeypatch)
    state = State.load(sidecar / "state.json")
    state.consecutive_gate_fails = 2
    state.save(sidecar / "state.json")
    _write_semantic(sidecar, verdict="fail", score=0.40)
    rc = main(["gate", "demo", "semantic"])
    assert rc != 0
    state = State.load(sidecar / "state.json")
    assert state.phase == "stuck"
    assert state.consecutive_gate_fails == 3


def test_semantic_gate_pass_resets_consec_fails(
    tmp_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sidecar = _seed_evaluate_phase(tmp_project, monkeypatch)
    state = State.load(sidecar / "state.json")
    state.consecutive_gate_fails = 2
    state.save(sidecar / "state.json")
    _write_semantic(sidecar, verdict="pass", score=0.92)
    rc = main(["gate", "demo", "semantic"])
    assert rc == 0
    state = State.load(sidecar / "state.json")
    assert state.consecutive_gate_fails == 0
    assert state.phase == "finalize"


def test_semantic_gate_malformed_json_exits_usage_error(
    tmp_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sidecar = _seed_evaluate_phase(tmp_project, monkeypatch)
    (sidecar / "evaluation").mkdir(parents=True, exist_ok=True)
    (sidecar / "evaluation" / "semantic.json").write_text("{not json")
    rc = main(["gate", "demo", "semantic"])
    assert rc != 0


def test_semantic_gate_invalid_verdict_value_rejected(
    tmp_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sidecar = _seed_evaluate_phase(tmp_project, monkeypatch)
    _write_semantic(sidecar, verdict="maybe", score=0.5)
    rc = main(["gate", "demo", "semantic"])
    assert rc != 0
