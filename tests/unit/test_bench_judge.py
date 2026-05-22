"""File-backed SimilarityProvider — score를 미리 산출한 JSON에서 읽는다.

3-Lane 분리를 지키기 위해 *deterministic CLI는 LLM 직접 호출 금지*. 외부
(skill/agent/사람)가 점수 파일을 작성하면 CLI는 그 파일만 읽어 callback에 주입.
"""
from pathlib import Path
import json
import pytest
from mimiron.bench.judge import JudgeError, load_similarity_from_file


def _write(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_valid_file_returns_callable_with_score(tmp_path: Path) -> None:
    p = tmp_path / "judge.json"
    _write(p, {"score": 0.85, "rationale": "actual covers all touched files"})
    provider = load_similarity_from_file(p)
    assert callable(provider)
    assert provider("actual diff text", "expected diff text") == pytest.approx(0.85)


def test_score_exact_boundaries_accepted(tmp_path: Path) -> None:
    p_lo = tmp_path / "lo.json"
    p_hi = tmp_path / "hi.json"
    _write(p_lo, {"score": 0.0})
    _write(p_hi, {"score": 1.0})
    assert load_similarity_from_file(p_lo)("a", "b") == 0.0
    assert load_similarity_from_file(p_hi)("a", "b") == 1.0


def test_score_below_zero_rejected(tmp_path: Path) -> None:
    p = tmp_path / "judge.json"
    _write(p, {"score": -0.1})
    with pytest.raises(JudgeError, match="score"):
        load_similarity_from_file(p)


def test_score_above_one_rejected(tmp_path: Path) -> None:
    p = tmp_path / "judge.json"
    _write(p, {"score": 1.5})
    with pytest.raises(JudgeError, match="score"):
        load_similarity_from_file(p)


def test_missing_score_key_rejected(tmp_path: Path) -> None:
    p = tmp_path / "judge.json"
    _write(p, {"rationale": "no score field"})
    with pytest.raises(JudgeError, match="score"):
        load_similarity_from_file(p)


def test_non_numeric_score_rejected(tmp_path: Path) -> None:
    p = tmp_path / "judge.json"
    _write(p, {"score": "high"})
    with pytest.raises(JudgeError, match="score"):
        load_similarity_from_file(p)


def test_malformed_json_rejected(tmp_path: Path) -> None:
    p = tmp_path / "judge.json"
    p.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(JudgeError, match="JSON"):
        load_similarity_from_file(p)


def test_missing_file_raises_file_not_found(tmp_path: Path) -> None:
    p = tmp_path / "nope.json"
    with pytest.raises(FileNotFoundError):
        load_similarity_from_file(p)


def test_returned_provider_is_stable_across_calls(tmp_path: Path) -> None:
    """같은 파일은 매 호출마다 같은 점수를 줘야 한다 (캐시 의존성 없이)."""
    p = tmp_path / "judge.json"
    _write(p, {"score": 0.42})
    provider = load_similarity_from_file(p)
    assert provider("x", "y") == 0.42
    assert provider("z", "w") == 0.42
