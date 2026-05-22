"""LLM 호출 인터페이스 + stub."""
from pathlib import Path
import pytest
from mimiron.llm import call_llm, median_of_3, LLMResponse


def test_stub_mode_reads_fixture(
    stub_mode: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fix = tmp_path / "f.md"
    fix.write_text("hello world")
    monkeypatch.setenv("MIMIRON_STUB_PATH", str(fix))
    r = call_llm(prompt="anything", purpose="clarify")
    assert isinstance(r, LLMResponse)
    assert r.text == "hello world"
    assert r.tokens_in >= 0
    assert r.tokens_out >= 0


def test_median_of_3_returns_middle_value() -> None:
    samples = [0.1, 0.5, 0.9]
    result = median_of_3(samples)
    assert result == 0.5


def test_median_of_3_handles_unsorted() -> None:
    assert median_of_3([0.9, 0.1, 0.5]) == 0.5


def test_median_of_3_requires_exactly_three() -> None:
    with pytest.raises(ValueError):
        median_of_3([0.1, 0.2])
