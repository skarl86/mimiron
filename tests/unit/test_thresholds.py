"""Thresholds.load_or_default — defaults + forward-compat (결함 #2)."""
from pathlib import Path
from mimiron.thresholds import Thresholds


def test_defaults_returns_known_values() -> None:
    t = Thresholds.defaults()
    assert t.ambiguity_max == 0.2
    assert t.spec_quality_min == 0.85
    assert t.max_parallel_workers == 4


def test_load_or_default_missing_file_returns_defaults(tmp_path: Path) -> None:
    t = Thresholds.load_or_default(tmp_path / "no-such.yaml")
    assert t.ambiguity_max == 0.2  # defaults 값


def test_load_or_default_partial_yaml_keeps_defaults_for_others(tmp_path: Path) -> None:
    p = tmp_path / "th.yaml"
    p.write_text("ambiguity_max: 0.15\n")
    t = Thresholds.load_or_default(p)
    assert t.ambiguity_max == 0.15
    assert t.spec_quality_min == 0.85  # 그대로


def test_load_or_default_ignores_unknown_keys(tmp_path: Path) -> None:
    """forward-compat: 미래 버전이 추가한 키가 있어도 *조용히 무시* (결함 #2)."""
    p = tmp_path / "th.yaml"
    p.write_text(
        "schema_version: 1\n"
        "ambiguity_max: 0.15\n"
        "future_flag_x: yes\n"
        "mutation_rule: 0.6\n"
    )
    t = Thresholds.load_or_default(p)
    assert t.ambiguity_max == 0.15
    # 알려진 default 값들은 유지
    assert t.spec_quality_min == 0.85
    assert t.max_parallel_workers == 4


def test_load_or_default_empty_yaml_returns_defaults(tmp_path: Path) -> None:
    p = tmp_path / "th.yaml"
    p.write_text("")
    t = Thresholds.load_or_default(p)
    assert t.ambiguity_max == 0.2
