"""mimiron init --bootstrap-toolchain — _global/ 부트스트랩.

결함 #1 fix: 신규 사용자가 evals/ fixture를 수동 복사하지 않아도
첫 init에서 mechanical gate가 즉시 작동 가능.
"""
import tomllib
import yaml
from pathlib import Path
import pytest
from mimiron.cli import main


def test_init_without_bootstrap_does_not_create_global(
    tmp_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """기본 동작은 변경되지 않음 — _global 자동 생성 안 함 (옵트인)."""
    # tmp_project fixture가 .mimiron/_global을 미리 만듦 — 빈 폴더로 떨궈
    (tmp_project / ".mimiron" / "_global" / "mechanical.toml").unlink(missing_ok=True)
    (tmp_project / ".mimiron" / "_global" / "thresholds.yaml").unlink(missing_ok=True)
    monkeypatch.chdir(tmp_project)
    main(["init", "demo"])
    g = tmp_project / ".mimiron" / "_global"
    assert not (g / "mechanical.toml").exists()


def test_init_with_bootstrap_python_uv_writes_mechanical_toml(
    tmp_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_project / ".mimiron" / "_global" / "mechanical.toml").unlink(missing_ok=True)
    monkeypatch.chdir(tmp_project)
    rc = main(["init", "demo", "--bootstrap-toolchain", "python-uv"])
    assert rc == 0
    toml_path = tmp_project / ".mimiron" / "_global" / "mechanical.toml"
    assert toml_path.exists()
    raw = tomllib.loads(toml_path.read_text())
    names = {c.get("name") for c in raw["checks"]}
    assert {"pytest", "ruff", "mypy"} <= names


def test_init_with_bootstrap_creates_default_thresholds(
    tmp_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_project / ".mimiron" / "_global" / "thresholds.yaml").unlink(missing_ok=True)
    monkeypatch.chdir(tmp_project)
    main(["init", "demo", "--bootstrap-toolchain", "python-uv"])
    th = tmp_project / ".mimiron" / "_global" / "thresholds.yaml"
    assert th.exists()
    raw = yaml.safe_load(th.read_text())
    assert raw["ambiguity_max"] == 0.2
    assert raw["spec_quality_min"] == 0.85


def test_init_with_bootstrap_preserves_existing_files(
    tmp_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """이미 _global/이 있으면 *덮어쓰지 않음* (사용자 결정 보존)."""
    monkeypatch.chdir(tmp_project)
    toml_path = tmp_project / ".mimiron" / "_global" / "mechanical.toml"
    toml_path.write_text("# user's custom toml\n[[checks]]\nname='custom'\ncommand='echo'\n")
    main(["init", "demo", "--bootstrap-toolchain", "python-uv"])
    # 사용자 내용 그대로
    assert "user's custom toml" in toml_path.read_text()


def test_init_bootstrap_supports_multiple_toolchains(
    tmp_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for chain in ("python-uv", "python-pip", "node-npm", "go"):
        sub = tmp_project / chain
        sub.mkdir(exist_ok=True)
        monkeypatch.chdir(sub)
        rc = main(["init", "demo", "--bootstrap-toolchain", chain])
        assert rc == 0, f"bootstrap {chain} failed"
        toml_path = sub / ".mimiron" / "_global" / "mechanical.toml"
        assert toml_path.exists(), f"mechanical.toml missing for {chain}"


def test_init_bootstrap_invalid_toolchain_rejected(
    tmp_project: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_project)
    rc = main(["init", "demo", "--bootstrap-toolchain", "no-such-chain"])
    assert rc != 0
