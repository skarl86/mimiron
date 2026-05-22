"""공용 pytest fixture."""
import os
import pytest
from pathlib import Path


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """`.mimiron/`이 있는 가짜 프로젝트 디렉토리."""
    (tmp_path / ".mimiron").mkdir()
    (tmp_path / ".mimiron" / "_global").mkdir()
    return tmp_path


@pytest.fixture
def stub_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """MIMIRON_STUB=1을 켠다 (LLM 호출 대신 fixture 읽음)."""
    monkeypatch.setenv("MIMIRON_STUB", "1")


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"
