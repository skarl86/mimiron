"""yaml_compat 라운드트립 + 타입별 스칼라 처리 + 중첩 케이스 검증 (C11)."""
from __future__ import annotations

import pathlib
import textwrap

import pytest

from mimiron.yaml_compat import YAMLError, safe_dump, safe_load


# ---------------------------------------------------------------------------
# Round-trip: scalars
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        False,
        0,
        1,
        -1,
        42,
        1.5,
        -0.25,
        "hello",
        "",
        "with spaces",
    ],
)
def test_roundtrip_scalars(value: object) -> None:
    text = safe_dump({"k": value})
    loaded = safe_load(text)
    assert loaded == {"k": value}, f"value={value!r} text={text!r} loaded={loaded!r}"


@pytest.mark.parametrize(
    "value",
    [
        # Strings that look like other types — must survive as strings after quoting.
        "true",
        "false",
        "null",
        "42",
        "1.5",
        "~",
        "yes",
        "no",
    ],
)
def test_roundtrip_string_that_looks_like_other_type(value: str) -> None:
    """Strings that would parse as bool/int/float/null must be quoted on dump
    so they round-trip as strings."""
    text = safe_dump({"k": value})
    loaded = safe_load(text)
    assert loaded == {"k": value}
    assert isinstance(loaded["k"], str)


def test_roundtrip_unicode() -> None:
    data = {"name": "한글", "emoji": "中文 ascii"}
    out = safe_dump(data)
    assert safe_load(out) == data


# ---------------------------------------------------------------------------
# Round-trip: collections
# ---------------------------------------------------------------------------


def test_roundtrip_nested_mapping() -> None:
    data = {"a": 1, "b": {"c": 2, "d": {"e": 3}}}
    assert safe_load(safe_dump(data)) == data


def test_roundtrip_list_of_dicts() -> None:
    """plan.yaml shape — what mimiron actually serializes."""
    data = {
        "tasks": [
            {"id": "T01", "owned_files": ["a.py", "b.py"], "worker": "worker"},
            {"id": "T02", "owned_files": ["c.py"], "depends_on": ["T01"]},
        ]
    }
    assert safe_load(safe_dump(data)) == data


def test_roundtrip_list_of_scalars() -> None:
    data = {"items": [1, 2, 3, "a", "b", True, None]}
    assert safe_load(safe_dump(data)) == data


def test_roundtrip_empty_collections() -> None:
    data = {"empty_list": [], "empty_dict": {}}
    assert safe_load(safe_dump(data)) == data


def test_roundtrip_deeply_nested() -> None:
    data = {"a": {"b": {"c": {"d": {"e": {"f": "leaf"}}}}}}
    assert safe_load(safe_dump(data)) == data


def test_roundtrip_top_level_list() -> None:
    data = [{"id": "T01"}, {"id": "T02"}]
    assert safe_load(safe_dump(data)) == data


def test_dump_sort_keys_alphabetical() -> None:
    data = {"z": 1, "a": 2, "m": 3}
    out = safe_dump(data, sort_keys=True)
    # Keys should appear in alphabetical order in the output.
    a_pos = out.index("a:")
    m_pos = out.index("m:")
    z_pos = out.index("z:")
    assert a_pos < m_pos < z_pos


def test_dump_preserves_insertion_order_by_default() -> None:
    data = {"z": 1, "a": 2, "m": 3}
    out = safe_dump(data)
    z_pos = out.index("z:")
    a_pos = out.index("a:")
    m_pos = out.index("m:")
    assert z_pos < a_pos < m_pos


# ---------------------------------------------------------------------------
# Parsing: external corpora shapes
# ---------------------------------------------------------------------------


def test_parse_pyyaml_compact_form() -> None:
    """PyYAML's safe_dump emits keys in compact-sequence style — we must read it."""
    text = textwrap.dedent(
        """\
        tasks:
        - depends_on: []
          id: T01
          owned_files:
          - somefile.py
          title: foo
          worker: worker
        - depends_on:
          - T01
          id: T02
          owned_files:
          - other.py
          title: bar
          worker: tester
        """
    )
    parsed = safe_load(text)
    assert isinstance(parsed, dict)
    assert len(parsed["tasks"]) == 2
    assert parsed["tasks"][0]["id"] == "T01"
    assert parsed["tasks"][0]["depends_on"] == []
    assert parsed["tasks"][1]["depends_on"] == ["T01"]
    assert parsed["tasks"][1]["worker"] == "tester"


def test_parse_inline_flow_sequence_of_scalars() -> None:
    """Existing mimiron plan.yaml uses ``depends_on: [T01, T02]`` style."""
    text = "depends_on: [T01, T02]"
    assert safe_load(text) == {"depends_on": ["T01", "T02"]}


def test_parse_empty_flow_sequence() -> None:
    assert safe_load("items: []") == {"items": []}


def test_parse_empty_flow_mapping() -> None:
    assert safe_load("items: {}") == {"items": {}}


# ---------------------------------------------------------------------------
# Parsing: block scalars
# ---------------------------------------------------------------------------


def test_parse_literal_block_scalar() -> None:
    text = textwrap.dedent(
        """\
        notes: |
          line one
          line two
        """
    )
    out = safe_load(text)
    assert out == {"notes": "line one\nline two"}


def test_parse_folded_block_scalar() -> None:
    text = textwrap.dedent(
        """\
        desc: >
          fold to
          one line
        """
    )
    out = safe_load(text)
    assert out["desc"].rstrip() == "fold to one line"


def test_literal_block_scalar_value_roundtrips_via_dump_then_load() -> None:
    """Dump emits double-quoted form, not ``|``, but the *value* must survive."""
    data = {"notes": "line one\nline two"}
    out = safe_dump(data)
    assert safe_load(out) == data


# ---------------------------------------------------------------------------
# Parsing: comments
# ---------------------------------------------------------------------------


def test_parse_full_line_comment() -> None:
    text = textwrap.dedent(
        """\
        # this is a comment
        key: value
        """
    )
    assert safe_load(text) == {"key": "value"}


def test_parse_inline_comment() -> None:
    text = "key: value  # inline comment"
    assert safe_load(text) == {"key": "value"}


def test_hash_inside_quoted_string_is_not_a_comment() -> None:
    text = 'message: "hello # not a comment"'
    assert safe_load(text) == {"message": "hello # not a comment"}


# ---------------------------------------------------------------------------
# Parsing: empty / null variants
# ---------------------------------------------------------------------------


def test_empty_document() -> None:
    assert safe_load("") is None


def test_comment_only_document() -> None:
    assert safe_load("# only a comment") is None


def test_whitespace_only_document() -> None:
    assert safe_load("   \n\n   \n") is None


@pytest.mark.parametrize("rep", ["null", "Null", "NULL", "~", ""])
def test_null_variants(rep: str) -> None:
    text = f"k: {rep}"
    assert safe_load(text) == {"k": None}


@pytest.mark.parametrize("rep", ["true", "True", "TRUE", "yes", "Yes", "YES"])
def test_bool_true_variants(rep: str) -> None:
    text = f"k: {rep}"
    assert safe_load(text) == {"k": True}


@pytest.mark.parametrize("rep", ["false", "False", "FALSE", "no", "No", "NO"])
def test_bool_false_variants(rep: str) -> None:
    text = f"k: {rep}"
    assert safe_load(text) == {"k": False}


# ---------------------------------------------------------------------------
# Parsing: anchors / aliases (read-only)
# ---------------------------------------------------------------------------


def test_anchor_and_alias_basic() -> None:
    text = textwrap.dedent(
        """\
        defaults: &defaults
          a: 1
          b: 2
        copy: *defaults
        """
    )
    parsed = safe_load(text)
    assert parsed == {"defaults": {"a": 1, "b": 2}, "copy": {"a": 1, "b": 2}}


def test_forward_alias_raises() -> None:
    """Alias before anchor must raise — we resolve in line order."""
    with pytest.raises(YAMLError):
        safe_load("a: *unknown")


# ---------------------------------------------------------------------------
# Parsing: error handling
# ---------------------------------------------------------------------------


def test_tabs_in_indent_raises() -> None:
    with pytest.raises(YAMLError, match="tabs"):
        safe_load("\tk: v")


# ---------------------------------------------------------------------------
# Smoke: parse real mimiron files
# ---------------------------------------------------------------------------


def test_parse_thresholds_yaml() -> None:
    """Smoke-parse the global thresholds file if present in the repo."""
    p = pathlib.Path(__file__).parent.parent.parent / ".mimiron" / "_global" / "thresholds.yaml"
    if not p.exists():
        pytest.skip("thresholds.yaml not present in repo")
    data = safe_load(p.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert "ambiguity_max" in data


def test_parse_plugin_self_contained_plan_yaml() -> None:
    """Smoke-parse the in-repo plan.yaml — exercises real-world shape."""
    p = (
        pathlib.Path(__file__).parent.parent.parent
        / ".mimiron"
        / "plugin-self-contained"
        / "plan.yaml"
    )
    if not p.exists():
        pytest.skip("plan.yaml not present in repo")
    data = safe_load(p.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert "tasks" in data
    assert isinstance(data["tasks"], list)
