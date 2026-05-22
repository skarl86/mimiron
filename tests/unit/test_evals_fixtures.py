"""evals/ fixture sanity — TOML 구문 + checks[] 구조 검증."""
from pathlib import Path
import tomllib


EVALS_DIR = Path(__file__).parent.parent.parent / "evals"


def _all_toml_fixtures() -> list[Path]:
    return sorted(EVALS_DIR.glob("*.toml"))


def test_at_least_one_fixture_exists() -> None:
    fixtures = _all_toml_fixtures()
    assert fixtures, "evals/ should have at least one .toml fixture"


def test_all_fixtures_parse_as_toml() -> None:
    for path in _all_toml_fixtures():
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
        assert isinstance(raw, dict), f"{path}: TOML root must be a dict"


def test_all_fixtures_have_checks_array() -> None:
    for path in _all_toml_fixtures():
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
        checks = raw.get("checks")
        assert isinstance(checks, list), f"{path}: missing or non-list 'checks'"
        assert len(checks) >= 1, f"{path}: at least one check required"


def test_each_check_has_command() -> None:
    for path in _all_toml_fixtures():
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
        for i, c in enumerate(raw["checks"]):
            assert "command" in c, (
                f"{path} check #{i}: missing 'command'"
            )
            assert isinstance(c["command"], str), (
                f"{path} check #{i}: command must be a string"
            )


def test_python_uv_fixture_matches_mimirons_own_toolchain() -> None:
    """Mimiron 자체가 dogfood — python-uv.toml은 pytest+ruff+mypy."""
    raw = tomllib.loads((EVALS_DIR / "python-uv.toml").read_text(encoding="utf-8"))
    names = {c.get("name") for c in raw["checks"]}
    assert {"pytest", "ruff", "mypy"} <= names, (
        f"python-uv.toml should run pytest+ruff+mypy, got {names}"
    )


def test_readme_present() -> None:
    assert (EVALS_DIR / "README.md").exists()
