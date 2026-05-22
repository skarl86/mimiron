"""state.json 모델 단위 테스트."""
import json
from pathlib import Path
import pytest
from mimiron.state import State, SCHEMA_VERSION


def test_create_initializes_defaults() -> None:
    s = State.create(slug="hello")
    assert s.slug == "hello"
    assert s.phase == "clarify"
    assert s.persistent is True
    assert s.paused is False
    assert s.completed_task_ids == []
    assert s.retries == {}
    assert s.schema_version == SCHEMA_VERSION


def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    s = State.create(slug="trip")
    p = tmp_path / "state.json"
    s.save(p)
    loaded = State.load(p)
    assert loaded.slug == "trip"
    assert loaded.phase == "clarify"
    assert loaded.schema_version == SCHEMA_VERSION


def test_load_rejects_wrong_schema_version(tmp_path: Path) -> None:
    p = tmp_path / "state.json"
    p.write_text(json.dumps({"schema_version": 999, "slug": "x", "phase": "clarify"}))
    with pytest.raises(ValueError, match="schema_version"):
        State.load(p)


def test_load_rejects_invalid_phase(tmp_path: Path) -> None:
    s = State.create(slug="x")
    p = tmp_path / "state.json"
    s.save(p)
    raw = json.loads(p.read_text())
    raw["phase"] = "not-a-phase"
    p.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="phase"):
        State.load(p)
