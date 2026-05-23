"""stdlib-only YAML reader/writer for the subset used by mimiron.

Supports block-style mappings, sequences, and scalars (int/float/bool/null/str
with optional quoting), plus ``#`` comments. Indentation must be spaces only
(>= 2 per level, consistent within a document); tabs are forbidden. Anchors/
aliases (``&foo``, ``*foo``) and explicit type tags (``!!str``) are **not**
supported — see constraint C04 in the plugin-self-contained spec.

Block-scalar notes (read-only extension over strict C04):
  * ``|`` (literal block scalar) is *read*: newlines are preserved exactly,
    the common leading indent is stripped, and the final trailing newline is
    stripped (default chomping). The result is a plain Python ``str``.
  * ``>`` (folded block scalar) is *read*: single line breaks are folded to
    spaces, consecutive blank lines collapse to a single ``\\n`` separator.
  * ``safe_dump`` never emits ``|`` / ``>`` — multi-line strings are written
    as double-quoted scalars (``"line1\\nline2"``). Round-trip via dump→load
    therefore yields the same Python string, but not the same YAML source.
    Block scalars exist solely so external corpora (e.g. benchmark.yaml
    ``notes: |``) keep parsing after PyYAML is removed.

Flow-style notes (pragmatic extension over strict C04):
  * ``[]`` and ``{}`` (empty flow collections) are read and written.
  * **One-line flow-style sequences of scalars** (``[a, b, c]``) are *read*
    but never written by ``safe_dump`` — block style is emitted. This keeps
    existing mimiron plan.yaml files (which use ``depends_on: [T01]`` style)
    parseable while honoring C05 round-trip for our own output.
  * Flow-style mappings (``{k: v}`` with content) and nested flow collections
    remain unsupported.

Anchor/alias notes (read-only extension over strict C04):
  * ``&name`` (anchor) on a value-position is *read*: the parsed value is
    registered under ``name`` and returned as-is. Anchors on bare scalars
    (``key: &id001 foo``), on block-collection values (``key: &id001`` with a
    nested block below), and on sequence items (``- &id001 ...``) are all
    accepted.
  * ``*name`` (alias) is *read*: the previously registered value is
    substituted. Forward references (alias before anchor) raise ``YAMLError``.
  * ``safe_dump`` never emits anchors/aliases — shared Python objects are
    written as independent block-style copies. Round-trip via dump→load
    therefore yields the same Python value, but not the same YAML source.
    Anchor/alias support exists solely so external corpora (e.g. PyYAML's
    ``safe_dump`` output for plans with shared lists) keeps parsing after
    PyYAML is removed.

The public API is intentionally a near-drop-in for the small slice of
``yaml.safe_load`` / ``yaml.safe_dump`` that mimiron uses::

    from mimiron import yaml_compat as yaml
    data = yaml.safe_load(text)
    out = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)

Round-trip guarantee (C05): for any object ``d`` producible by ``safe_load``
*without block scalars*, ``safe_load(safe_dump(d)) == d``. Inputs containing
``|``/``>`` block scalars round-trip in value but not in source form, since
the dumper emits double-quoted form.
"""
from __future__ import annotations

import re
from typing import Any

__all__ = ["safe_load", "safe_dump", "YAMLError"]


class YAMLError(ValueError):
    """Raised on malformed input that the supported subset cannot represent."""


# ---------------------------------------------------------------------------
# Scalar parsing
# ---------------------------------------------------------------------------

_INT_RE = re.compile(r"^-?\d+$")
_FLOAT_RE = re.compile(
    r"^-?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?$"
)
# Note: _FLOAT_RE accepts plain integers too — we check _INT_RE first.

_BOOL_TRUE = {"true", "True", "TRUE", "yes", "Yes", "YES"}
_BOOL_FALSE = {"false", "False", "FALSE", "no", "No", "NO"}
_NULL = {"null", "Null", "NULL", "~", ""}


def _split_flow_items(inner: str) -> list[str]:
    """Split the inside of a flow sequence on top-level commas.

    Respects ``"..."`` and ``'...'`` quoted strings. Does NOT support nested
    flow collections (per C04, only one-level flow sequences of scalars are
    accepted by the reader).
    """
    items: list[str] = []
    buf: list[str] = []
    in_single = False
    in_double = False
    for i, ch in enumerate(inner):
        if ch == '"' and not in_single:
            if in_double and i > 0 and inner[i - 1] == "\\":
                buf.append(ch)
                continue
            in_double = not in_double
            buf.append(ch)
        elif ch == "'" and not in_double:
            in_single = not in_single
            buf.append(ch)
        elif ch == "," and not in_single and not in_double:
            items.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    items.append("".join(buf))
    return items


def _decode_double_quoted(body: str) -> str:
    """Decode escapes inside a double-quoted scalar body (quotes already stripped)."""
    out: list[str] = []
    i = 0
    n = len(body)
    while i < n:
        ch = body[i]
        if ch == "\\" and i + 1 < n:
            nxt = body[i + 1]
            mapping = {
                "n": "\n",
                "t": "\t",
                "r": "\r",
                '"': '"',
                "'": "'",
                "\\": "\\",
                "0": "\0",
                "/": "/",
                "b": "\b",
                "f": "\f",
            }
            if nxt in mapping:
                out.append(mapping[nxt])
                i += 2
                continue
            if nxt == "x" and i + 3 < n:
                out.append(chr(int(body[i + 2 : i + 4], 16)))
                i += 4
                continue
            if nxt == "u" and i + 5 < n:
                out.append(chr(int(body[i + 2 : i + 6], 16)))
                i += 6
                continue
            # Unknown escape — keep as-is (forgiving).
            out.append(ch)
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _parse_scalar(raw: str) -> Any:
    """Convert a raw scalar token (already stripped of surrounding whitespace) into a Python value."""
    s = raw
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        return _decode_double_quoted(s[1:-1])
    if len(s) >= 2 and s[0] == "'" and s[-1] == "'":
        # Single-quoted: only '' → ' escape, no other escapes.
        return s[1:-1].replace("''", "'")
    # Recognize the only two flow-style tokens we ever emit: empty list / dict.
    # Our own dumper produces ``[]`` and ``{}`` for empty collections.
    if s == "[]":
        return []
    if s == "{}":
        return {}
    # Pragmatic extension: one-line flow sequence of scalars, e.g. ``[T01, T02]``.
    # Existing mimiron plan.yaml files use this style for depends_on; we read it
    # but never emit it (safe_dump uses block style).
    if len(s) >= 2 and s[0] == "[" and s[-1] == "]":
        inner = s[1:-1].strip()
        if inner == "":
            return []
        # Split on commas, but respect quoted strings.
        items = _split_flow_items(inner)
        return [_parse_scalar(item.strip()) for item in items]
    if s in _NULL:
        return None
    if s in _BOOL_TRUE:
        return True
    if s in _BOOL_FALSE:
        return False
    if _INT_RE.match(s):
        try:
            return int(s)
        except ValueError:
            return s
    if _FLOAT_RE.match(s) and not _INT_RE.match(s):
        try:
            return float(s)
        except ValueError:
            return s
    return s


# ---------------------------------------------------------------------------
# Line preprocessing
# ---------------------------------------------------------------------------


def _strip_inline_comment(line: str) -> str:
    """Remove inline ``# comment`` from a line, respecting quoted strings.

    A ``#`` only starts a comment when preceded by whitespace (or at column 0,
    handled by the caller before calling this). Inside ``"..."`` / ``'...'``
    quotes, ``#`` is literal.
    """
    in_single = False
    in_double = False
    prev = " "  # treat start-of-string as preceded by whitespace
    for i, ch in enumerate(line):
        if ch == '"' and not in_single:
            # Honor escapes inside double-quoted strings.
            if in_double and line[i - 1] == "\\":
                pass
            else:
                in_double = not in_double
        elif ch == "'" and not in_double:
            in_single = not in_single
        elif ch == "#" and not in_single and not in_double and prev.isspace():
            return line[:i].rstrip()
        prev = ch
    return line.rstrip()


_BLOCK_SCALAR_RE = re.compile(r"^(?P<head>.*[:\-])\s+(?P<style>[|>])\s*$")


def _resolve_block_scalar(
    raw_lines: list[str],
    start_idx: int,
    parent_indent: int,
    style: str,
    start_line_no: int,
) -> tuple[str, int]:
    """Resolve a ``|`` or ``>`` block scalar starting after ``start_idx``.

    ``parent_indent`` is the column of the key (or ``-`` marker) introducing the
    block scalar. Content lines must be indented strictly deeper than that.
    Reads forward through ``raw_lines`` until a non-blank line at indent
    ``<= parent_indent`` is found (or EOF), and returns
    ``(resolved_string, next_idx)`` where ``next_idx`` is the index of the
    first line NOT consumed by the block scalar.

    Default chomping is applied: a single trailing newline is stripped from
    the final result (matches YAML 1.1 ``|`` / ``>`` with no chomping
    indicator).
    """
    # First pass: detect block indent (column of first non-blank content line).
    i = start_idx
    block_indent: int | None = None
    while i < len(raw_lines):
        raw = raw_lines[i]
        if raw.strip() == "":
            i += 1
            continue
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise YAMLError(
                f"line {start_line_no + (i - start_idx)}: tabs are not allowed in indentation"
            )
        indent = len(raw) - len(raw.lstrip(" "))
        if indent <= parent_indent:
            # Block scalar is empty (no indented content followed).
            return ("", start_idx)
        block_indent = indent
        break

    if block_indent is None:
        # EOF reached without any content.
        return ("", len(raw_lines))

    # Second pass: collect lines belonging to the block scalar.
    collected: list[str] = []  # entries are the de-indented content (may be "")
    j = start_idx
    while j < len(raw_lines):
        raw = raw_lines[j]
        if raw.strip() == "":
            collected.append("")
            j += 1
            continue
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise YAMLError(
                f"line {start_line_no + (j - start_idx)}: tabs are not allowed in indentation"
            )
        indent = len(raw) - len(raw.lstrip(" "))
        if indent < block_indent:
            # End of block scalar — but it's only ended if this line is also
            # not-deeper-than parent. Since block_indent > parent_indent, any
            # indent < block_indent that is also <= parent_indent terminates.
            if indent <= parent_indent:
                break
            # Otherwise this is inconsistent indentation inside the block.
            raise YAMLError(
                f"line {start_line_no + (j - start_idx)}: "
                f"block scalar content under-indented (expected >= {block_indent})"
            )
        # Strip the common block_indent prefix (preserve any deeper indent).
        collected.append(raw[block_indent:])
        j += 1

    # Trim trailing blank entries (default chomping = strip trailing newlines).
    while collected and collected[-1] == "":
        collected.pop()

    if style == "|":
        return ("\n".join(collected), j)

    # Folded ('>'): single line breaks fold to ' ', consecutive blanks → '\n' per blank-run.
    result_parts: list[str] = []
    pending_blanks = 0
    for line in collected:
        if line == "":
            pending_blanks += 1
            continue
        if not result_parts:
            result_parts.append(line)
        elif pending_blanks > 0:
            # One blank line → one '\n'; N blanks → N '\n'.
            result_parts.append("\n" * pending_blanks)
            result_parts.append(line)
        else:
            result_parts.append(" ")
            result_parts.append(line)
        pending_blanks = 0
    return ("".join(result_parts), j)


def _preprocess(text: str) -> list[tuple[int, int, str]]:
    """Split text into significant lines.

    Returns a list of ``(line_no, indent, content)`` tuples for non-empty,
    non-comment lines. ``line_no`` is 1-based (for error messages).

    Block scalars (``|``, ``>``) are resolved here: when a line ends with
    ``: |`` / ``: >`` / ``- |`` / ``- >``, the following indented lines are
    consumed and the value is rewritten as a double-quoted scalar so the
    downstream parser stays unchanged.
    """
    raw_lines = text.splitlines()
    out: list[tuple[int, int, str]] = []
    i = 0
    while i < len(raw_lines):
        line_no = i + 1
        raw = raw_lines[i]
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise YAMLError(f"line {line_no}: tabs are not allowed in indentation")
        stripped = raw.lstrip(" ")
        if not stripped or stripped.startswith("#"):
            i += 1
            continue
        indent = len(raw) - len(stripped)
        content = _strip_inline_comment(stripped)
        if not content:
            i += 1
            continue

        # Detect a trailing block-scalar indicator: ``... :  |`` or ``... :  >``
        # (also for sequence items ``- |``). We require the indicator to be
        # the last non-whitespace token on the line.
        m = _BLOCK_SCALAR_RE.match(content)
        if m is not None:
            head = m.group("head").rstrip()
            style = m.group("style")
            # Block content lines must be indented deeper than this key/marker.
            resolved, next_i = _resolve_block_scalar(
                raw_lines,
                start_idx=i + 1,
                parent_indent=indent,
                style=style,
                start_line_no=line_no + 1,
            )
            # Re-emit as ``head value`` where value is a double-quoted scalar
            # of the resolved string (downstream parser handles decode).
            quoted = _encode_double_quoted(resolved, allow_unicode=True)
            new_content = f"{head} {quoted}"
            out.append((line_no, indent, new_content))
            i = next_i
            continue

        out.append((line_no, indent, content))
        i += 1
    return out


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


class _Cursor:
    __slots__ = ("lines", "pos", "anchors")

    def __init__(self, lines: list[tuple[int, int, str]]) -> None:
        self.lines = lines
        self.pos = 0
        # Anchor registry for ``&name`` / ``*name`` resolution. Populated as
        # values are parsed; aliases are resolved against this dict in line
        # order, so forward references (alias before anchor) raise YAMLError.
        self.anchors: dict[str, Any] = {}

    def peek(self) -> tuple[int, int, str] | None:
        if self.pos >= len(self.lines):
            return None
        return self.lines[self.pos]

    def consume(self) -> tuple[int, int, str]:
        item = self.lines[self.pos]
        self.pos += 1
        return item


_ANCHOR_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_\-]*")


def _split_anchor_or_alias(value_raw: str) -> tuple[str | None, str | None, str]:
    """Strip a leading ``&name`` (anchor) or ``*name`` (alias) token.

    Returns ``(anchor_name, alias_name, remainder)``:
      * anchor present: ``(name, None, remaining_value_after_anchor_token)``
      * alias present:  ``(None, name, remaining)`` (alias must be the whole
        value — any non-whitespace remainder triggers YAMLError).
      * neither:        ``(None, None, value_raw)``
    """
    if not value_raw:
        return (None, None, value_raw)
    if value_raw[0] not in "&*":
        return (None, None, value_raw)
    is_alias = value_raw[0] == "*"
    m = _ANCHOR_NAME_RE.match(value_raw[1:])
    if m is None:
        # Stray '&'/'*' without a valid name — treat as plain text.
        return (None, None, value_raw)
    name = m.group(0)
    remainder = value_raw[1 + len(name) :].lstrip(" ")
    if is_alias:
        if remainder != "":
            raise YAMLError(f"alias *{name} cannot have a trailing value: {value_raw!r}")
        return (None, name, "")
    return (name, None, remainder)


def _resolve_alias(cur: _Cursor, line_no: int, name: str) -> Any:
    if name not in cur.anchors:
        raise YAMLError(
            f"line {line_no}: alias *{name} references unknown anchor"
        )
    return cur.anchors[name]


def _split_key_value(content: str) -> tuple[str, str] | None:
    """Split a ``key: value`` line. Returns (key, value) or None if no ``:`` found.

    Honors quoted keys and ignores ``:`` inside quotes. The separator must be
    ``:`` followed by space or end-of-string.
    """
    in_single = False
    in_double = False
    n = len(content)
    for i, ch in enumerate(content):
        if ch == '"' and not in_single:
            if in_double and i > 0 and content[i - 1] == "\\":
                pass
            else:
                in_double = not in_double
        elif ch == "'" and not in_double:
            in_single = not in_single
        elif ch == ":" and not in_single and not in_double:
            if i + 1 == n or content[i + 1] == " ":
                key = content[:i].rstrip()
                value = content[i + 1 :].lstrip()
                return key, value
    return None


def _parse_block(cur: _Cursor, indent: int) -> Any:
    """Parse a block (mapping or sequence) where every line has ``line_indent >= indent``.

    Stops when a line with smaller indent is encountered (or EOF).
    """
    head = cur.peek()
    if head is None:
        return None
    _, head_indent, head_content = head
    if head_indent < indent:
        return None

    if head_content.startswith("- ") or head_content == "-":
        return _parse_sequence(cur, head_indent)
    return _parse_mapping(cur, head_indent)


def _parse_mapping(cur: _Cursor, indent: int) -> dict[str, Any]:
    result: dict[str, Any] = {}
    while True:
        item = cur.peek()
        if item is None:
            break
        line_no, line_indent, content = item
        if line_indent < indent:
            break
        if line_indent > indent:
            raise YAMLError(f"line {line_no}: unexpected indentation in mapping")
        if content.startswith("- ") or content == "-":
            # A sibling sequence item at the same indent ends this mapping
            # only if it's at a *parent* level; at this level it means malformed.
            raise YAMLError(f"line {line_no}: sequence item inside mapping at same indent")

        kv = _split_key_value(content)
        if kv is None:
            raise YAMLError(f"line {line_no}: expected 'key: value', got {content!r}")
        key_raw, value_raw = kv
        key = _parse_scalar(key_raw)
        if not isinstance(key, str):
            # YAML allows non-string keys; we restrict to strings.
            key = str(key_raw)
        cur.consume()

        result[key] = _resolve_value(cur, line_no, value_raw, indent)
    return result


def _resolve_value(
    cur: _Cursor, line_no: int, value_raw: str, parent_indent: int
) -> Any:
    """Resolve a mapping/inline-mapping value, honoring ``&anchor`` and ``*alias``.

    ``parent_indent`` is the column of the key whose value we're resolving;
    nested block content must be strictly deeper than that (or, for PyYAML
    compact-style sequences, at the same column as the key — handled below).
    """
    anchor, alias, remainder = _split_anchor_or_alias(value_raw)
    if alias is not None:
        return _resolve_alias(cur, line_no, alias)
    value: Any
    if remainder != "":
        value = _parse_scalar(remainder)
    else:
        # No inline value — look at next line for a nested block, possibly at
        # the same indent as the parent key (PyYAML compact dump style).
        nxt = cur.peek()
        if nxt is None:
            value = None
        elif nxt[1] > parent_indent:
            value = _parse_block(cur, nxt[1])
        elif nxt[1] == parent_indent and (
            nxt[2].startswith("- ") or nxt[2] == "-"
        ):
            value = _parse_sequence(cur, parent_indent)
        else:
            value = None
    if anchor is not None:
        cur.anchors[anchor] = value
    return value


def _parse_sequence(cur: _Cursor, indent: int) -> list[Any]:
    result: list[Any] = []
    while True:
        item = cur.peek()
        if item is None:
            break
        line_no, line_indent, content = item
        if line_indent < indent:
            break
        if line_indent > indent:
            raise YAMLError(f"line {line_no}: unexpected indentation in sequence")
        if not (content.startswith("- ") or content == "-"):
            break

        cur.consume()
        if content == "-":
            # Empty value or nested block on following lines.
            nxt = cur.peek()
            if nxt is None or nxt[1] <= indent:
                result.append(None)
            else:
                result.append(_parse_block(cur, nxt[1]))
            continue

        rest = content[2:]  # strip "- "
        # Detect a leading anchor/alias on the item itself: ``- &name ...`` or
        # ``- *name``. Aliases must be the whole item. Anchors prefix the
        # remaining content, which is then parsed normally and registered.
        item_anchor, item_alias, rest = _split_anchor_or_alias(rest)
        if item_alias is not None:
            result.append(_resolve_alias(cur, line_no, item_alias))
            continue

        # ``rest`` may be a scalar, or "key: value" starting an inline mapping.
        kv = _split_key_value(rest)
        if kv is None:
            # Plain scalar item (possibly with a preceding anchor).
            value = _parse_scalar(rest)
            if item_anchor is not None:
                cur.anchors[item_anchor] = value
            result.append(value)
            continue

        # Inline mapping: first key starts here, additional keys may follow
        # on next lines at indent = indent + 2 (column of first key).
        inline_key_col = indent + 2  # column where the first key begins (after "- ")
        first_key_raw, first_value_raw = kv
        first_key = _parse_scalar(first_key_raw)
        if not isinstance(first_key, str):
            first_key = str(first_key_raw)
        sub: dict[str, Any] = {}
        sub[first_key] = _resolve_value(cur, line_no, first_value_raw, inline_key_col)

        # Continue collecting sibling keys at inline_key_col.
        while True:
            nxt = cur.peek()
            if nxt is None:
                break
            n_line, n_indent, n_content = nxt
            if n_indent < inline_key_col:
                break
            if n_indent > inline_key_col:
                raise YAMLError(
                    f"line {n_line}: unexpected indentation inside inline-mapping sequence item"
                )
            if n_content.startswith("- ") or n_content == "-":
                break
            n_kv = _split_key_value(n_content)
            if n_kv is None:
                raise YAMLError(f"line {n_line}: expected 'key: value', got {n_content!r}")
            n_key_raw, n_value_raw = n_kv
            n_key = _parse_scalar(n_key_raw)
            if not isinstance(n_key, str):
                n_key = str(n_key_raw)
            cur.consume()
            sub[n_key] = _resolve_value(cur, n_line, n_value_raw, inline_key_col)

        if item_anchor is not None:
            cur.anchors[item_anchor] = sub
        result.append(sub)
    return result


def safe_load(text: str) -> Any:
    """Parse a YAML string (mimiron subset) and return the resulting Python object.

    Returns ``None`` for an empty document or a document containing only
    comments / whitespace, matching ``yaml.safe_load`` behavior.
    """
    lines = _preprocess(text)
    if not lines:
        return None
    cur = _Cursor(lines)
    # Top-level indent is the first line's indent (usually 0; we tolerate >0
    # only if the entire document is uniformly indented, which is unusual).
    top_indent = lines[0][1]
    result = _parse_block(cur, top_indent)
    if cur.pos != len(lines):
        line_no = lines[cur.pos][0]
        raise YAMLError(f"line {line_no}: extra content after document root")
    return result


# ---------------------------------------------------------------------------
# Dumper
# ---------------------------------------------------------------------------

# Characters / patterns that force quoting on a string scalar.
_NEEDS_QUOTE_CHARS = set(':#\n\t\r\f\b"\'`,[]{}&*!|>%@')
_LEADING_INDICATORS = set("-?!|>%@`")


def _string_needs_quoting(s: str) -> bool:
    if s == "":
        return True
    if s != s.strip():
        return True  # leading/trailing whitespace
    if s[0] in _LEADING_INDICATORS:
        return True
    # If the string would parse as something else, quote it.
    parsed = _parse_scalar(s)
    if not isinstance(parsed, str):
        return True
    if parsed != s:
        return True
    for ch in s:
        if ch in _NEEDS_QUOTE_CHARS:
            return True
        if ord(ch) < 0x20:  # control char
            return True
    # ': ' or trailing ':' would be ambiguous with key/value separator
    if ": " in s or s.endswith(":"):
        return True
    if " #" in s:
        return True
    return False


def _encode_double_quoted(s: str, allow_unicode: bool) -> str:
    out: list[str] = ['"']
    for ch in s:
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\t":
            out.append("\\t")
        elif ch == "\r":
            out.append("\\r")
        elif ord(ch) < 0x20:
            out.append(f"\\x{ord(ch):02x}")
        elif not allow_unicode and ord(ch) > 0x7E:
            cp = ord(ch)
            if cp <= 0xFFFF:
                out.append(f"\\u{cp:04x}")
            else:
                out.append(f"\\U{cp:08x}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def _format_scalar(value: Any, allow_unicode: bool) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        # Reasonably canonical float repr.
        if value != value:  # NaN
            return ".nan"
        if value == float("inf"):
            return ".inf"
        if value == float("-inf"):
            return "-.inf"
        return repr(value)
    if isinstance(value, str):
        if _string_needs_quoting(value):
            return _encode_double_quoted(value, allow_unicode)
        return value
    raise YAMLError(f"unsupported scalar type for dump: {type(value).__name__}")


def _is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (bool, int, float, str))


def _dump_node(
    value: Any,
    indent: int,
    *,
    allow_unicode: bool,
    sort_keys: bool,
) -> list[str]:
    """Emit lines (without trailing newlines) for a node at the given indent column."""
    pad = " " * indent
    if isinstance(value, dict):
        if not value:
            return [f"{pad}{{}}"]
        keys = sorted(value.keys()) if sort_keys else list(value.keys())
        lines: list[str] = []
        for k in keys:
            if not isinstance(k, str):
                raise YAMLError(f"non-string mapping key not supported: {k!r}")
            key_repr = _format_scalar(k, allow_unicode)
            v = value[k]
            if isinstance(v, dict):
                if not v:
                    lines.append(f"{pad}{key_repr}: {{}}")
                else:
                    lines.append(f"{pad}{key_repr}:")
                    lines.extend(
                        _dump_node(
                            v,
                            indent + 2,
                            allow_unicode=allow_unicode,
                            sort_keys=sort_keys,
                        )
                    )
            elif isinstance(v, list):
                if not v:
                    lines.append(f"{pad}{key_repr}: []")
                else:
                    lines.append(f"{pad}{key_repr}:")
                    lines.extend(
                        _dump_sequence(
                            v,
                            indent,
                            allow_unicode=allow_unicode,
                            sort_keys=sort_keys,
                        )
                    )
            else:
                lines.append(f"{pad}{key_repr}: {_format_scalar(v, allow_unicode)}")
        return lines
    if isinstance(value, list):
        if not value:
            return [f"{pad}[]"]
        return _dump_sequence(
            value, indent - 2 if indent >= 2 else 0,
            allow_unicode=allow_unicode,
            sort_keys=sort_keys,
        )
    # Bare scalar at top level.
    return [f"{pad}{_format_scalar(value, allow_unicode)}"]


def _dump_sequence(
    seq: list[Any],
    parent_indent: int,
    *,
    allow_unicode: bool,
    sort_keys: bool,
) -> list[str]:
    """Emit ``- item`` lines for a sequence.

    Items sit at ``parent_indent`` (same column as the parent key), so the
    ``-`` marker is at ``parent_indent`` and continuation content at
    ``parent_indent + 2``.
    """
    pad = " " * parent_indent
    lines: list[str] = []
    for item in seq:
        if isinstance(item, dict):
            if not item:
                lines.append(f"{pad}- {{}}")
                continue
            keys = sorted(item.keys()) if sort_keys else list(item.keys())
            first = True
            for k in keys:
                if not isinstance(k, str):
                    raise YAMLError(f"non-string mapping key not supported: {k!r}")
                key_repr = _format_scalar(k, allow_unicode)
                v = item[k]
                prefix = f"{pad}- " if first else f"{pad}  "
                first = False
                if isinstance(v, dict):
                    if not v:
                        lines.append(f"{prefix}{key_repr}: {{}}")
                    else:
                        lines.append(f"{prefix}{key_repr}:")
                        lines.extend(
                            _dump_node(
                                v,
                                parent_indent + 4,
                                allow_unicode=allow_unicode,
                                sort_keys=sort_keys,
                            )
                        )
                elif isinstance(v, list):
                    if not v:
                        lines.append(f"{prefix}{key_repr}: []")
                    else:
                        lines.append(f"{prefix}{key_repr}:")
                        lines.extend(
                            _dump_sequence(
                                v,
                                parent_indent + 2,
                                allow_unicode=allow_unicode,
                                sort_keys=sort_keys,
                            )
                        )
                else:
                    lines.append(f"{prefix}{key_repr}: {_format_scalar(v, allow_unicode)}")
        elif isinstance(item, list):
            if not item:
                lines.append(f"{pad}- []")
            else:
                lines.append(f"{pad}-")
                lines.extend(
                    _dump_sequence(
                        item,
                        parent_indent + 2,
                        allow_unicode=allow_unicode,
                        sort_keys=sort_keys,
                    )
                )
        else:
            lines.append(f"{pad}- {_format_scalar(item, allow_unicode)}")
    return lines


def safe_dump(
    data: Any,
    *,
    allow_unicode: bool = True,
    sort_keys: bool = False,
) -> str:
    """Serialize a Python object to a YAML string (mimiron subset).

    ``sort_keys=False`` (default) preserves dict insertion order; ``True`` sorts
    keys alphabetically. ``allow_unicode=True`` (default) emits non-ASCII chars
    verbatim; ``False`` escapes them with ``\\u`` / ``\\U`` sequences.
    """
    if data is None:
        return "null\n"
    if _is_scalar(data):
        return _format_scalar(data, allow_unicode) + "\n"
    if isinstance(data, dict) and not data:
        return "{}\n"
    if isinstance(data, list) and not data:
        return "[]\n"
    lines = _dump_node(data, 0, allow_unicode=allow_unicode, sort_keys=sort_keys)
    return "\n".join(lines) + "\n"
