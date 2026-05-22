"""LLM 호출 인터페이스.

v0 시점에 *실제* LLM 호출은 Claude Code skill 내부에서 Claude가 직접 수행한다.
이 모듈은 다음 역할만:
- MIMIRON_STUB=1 환경에서 fixture 파일을 LLM 응답으로 반환 (CI/unit test용)
- median_of_3 등 점수 안정화 헬퍼
- LLMResponse 데이터 클래스
"""
from __future__ import annotations

import os
import statistics
from dataclasses import dataclass
from pathlib import Path


@dataclass
class LLMResponse:
    text: str
    tokens_in: int
    tokens_out: int


def call_llm(*, prompt: str, purpose: str) -> LLMResponse:
    """v0: stub 모드만 결정적으로 처리. 실제 호출은 skill 안에서 Claude가 수행."""
    if os.environ.get("MIMIRON_STUB") == "1":
        path = os.environ.get("MIMIRON_STUB_PATH")
        if not path:
            raise RuntimeError(
                "MIMIRON_STUB=1 but MIMIRON_STUB_PATH not set. "
                "Set it to the fixture file to read."
            )
        text = Path(path).read_text(encoding="utf-8")
        return LLMResponse(text=text, tokens_in=len(prompt) // 4, tokens_out=len(text) // 4)
    raise NotImplementedError(
        "Direct LLM calls from CLI are out of scope for v0. "
        "Use MIMIRON_STUB=1 in tests, or invoke from a Claude Code skill."
    )


def median_of_3(samples: list[float]) -> float:
    if len(samples) != 3:
        raise ValueError(f"median_of_3 requires exactly 3 samples, got {len(samples)}")
    return statistics.median(samples)
