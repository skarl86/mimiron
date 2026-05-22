"""File-backed SimilarityProvider.

3-Lane 분리 정책상 deterministic CLI는 LLM을 직접 호출하지 않는다. 대신
외부 (skill, agent, 또는 사람)가 *judge artifact*를 미리 만들고 CLI는
그 파일만 읽어 점수를 callback으로 노출한다.

판정 파일 형식 (JSON):

    {
      "score": 0.0~1.0,           # 필수
      "rationale": "사유 텍스트"  # optional, 향후 audit용
    }
"""
from __future__ import annotations

import json
from pathlib import Path

from mimiron.bench.runner import SimilarityProvider


class JudgeError(ValueError):
    """판정 artifact 형식 오류."""


def load_similarity_from_file(path: Path) -> SimilarityProvider:
    """판정 JSON을 읽어 SimilarityProvider callable로 변환.

    호출 시점에 점수 산출은 *이미 끝나 있어야 한다*. 반환된 provider는
    호출 인자(actual, expected)를 무시하고 고정 점수를 돌려준다 — 외부에서
    파일을 갱신하지 않는 한 같은 점수.
    """
    text = path.read_text(encoding="utf-8")
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as e:
        raise JudgeError(f"judge file is not valid JSON: {e}") from e
    if not isinstance(raw, dict) or "score" not in raw:
        raise JudgeError("judge file must contain 'score' key")
    score = raw["score"]
    if not isinstance(score, (int, float)) or isinstance(score, bool):
        raise JudgeError(f"'score' must be a number, got {type(score).__name__}")
    if not 0.0 <= float(score) <= 1.0:
        raise JudgeError(f"'score' must be in [0.0, 1.0], got {score}")
    fixed = float(score)

    def _provider(_actual: str, _expected: str) -> float:
        return fixed

    return _provider
