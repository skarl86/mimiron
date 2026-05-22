"""mechanical gate runner."""
from pathlib import Path
from mimiron.gates import run_mechanical_gate


def test_mechanical_gate_passes_when_all_zero(tmp_path: Path, fixtures_dir: Path) -> None:
    v = run_mechanical_gate(
        toml_path=fixtures_dir / "mechanical_pass.toml",
        slug="x",
        cwd=tmp_path,
    )
    assert v.verdict == "pass"
    assert v.kind == "mechanical"
    assert v.details["checks"][0]["exit_code"] == 0


def test_mechanical_gate_fails_when_any_nonzero(tmp_path: Path, fixtures_dir: Path) -> None:
    v = run_mechanical_gate(
        toml_path=fixtures_dir / "mechanical_fail.toml",
        slug="x",
        cwd=tmp_path,
    )
    assert v.verdict == "fail"
    assert v.details["checks"][0]["exit_code"] != 0


def test_mechanical_gate_handles_missing_toml(tmp_path: Path) -> None:
    v = run_mechanical_gate(toml_path=tmp_path / "nope.toml", slug="x", cwd=tmp_path)
    assert v.verdict == "fail"
    assert "missing" in v.details.get("error", "").lower()
