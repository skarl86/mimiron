"""SWE-bench style test runner — FAIL_TO_PASS + PASS_TO_PASS pytest selector 측정."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

# pytest summary line: "N passed", "N failed", "N error"
_PASS_RE = re.compile(r"(\d+)\s+passed")
_FAIL_RE = re.compile(r"(\d+)\s+failed")
# pytest summary lines end with timing like " in 0.12s" or " in 1.23 seconds".
# Anchor to that suffix to avoid matching assertion messages in failure tracebacks
# (e.g. "AssertionError: expected 5 passed but got 0").
_SUMMARY_LINE_RE = re.compile(r"\bin\s+\d+(?:\.\d+)?\s*s(?:econds?)?\b")


def run_swebench_tests(
    *,
    meta_path: Path,
    repo_root: Path,
    timeout_s: int = 600,
) -> tuple[float, dict[str, Any]]:
    """meta_path 의 FAIL_TO_PASS+PASS_TO_PASS selector 를 repo_root 에서 pytest 로 실행.

    Returns: (test_pass_rate, details)
      - test_pass_rate ∈ [0.0, 1.0]: passed / total selectors
      - details: 디버깅용 메타 (reason 포함 가능)
    """
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    ftp = list(meta.get("FAIL_TO_PASS", []) or [])
    ptp = list(meta.get("PASS_TO_PASS", []) or [])
    selectors = ftp + ptp
    total = len(selectors)

    if total == 0:
        return 0.0, {"reason": "no_selectors", "selectors_total": 0, "selectors_passed": 0}

    cmd = ["pytest", "-q", "--no-header", *selectors]
    try:
        proc = subprocess.run(
            cmd, cwd=repo_root, capture_output=True, text=True,
            timeout=timeout_s, check=False,
        )
    except subprocess.TimeoutExpired:
        return 0.0, {
            "reason": "timeout", "selectors_total": total, "selectors_passed": 0,
            "timeout_s": timeout_s,
        }

    if proc.returncode in (2, 3, 4, 5):  # pytest collection / usage / internal error
        return 0.0, {
            "reason": "env_error", "selectors_total": total, "selectors_passed": 0,
            "stderr_tail": proc.stderr[-500:],
        }

    # Only scan lines that look like pytest summary lines (contain " in N.Ns" timing)
    # to avoid false positives from assertion messages in failure tracebacks
    # (e.g. "AssertionError: expected 5 passed but got 0"). Use last such line.
    summary_lines = [ln for ln in proc.stdout.splitlines() if _SUMMARY_LINE_RE.search(ln)]
    summary = summary_lines[-1] if summary_lines else ""
    passed_matches = _PASS_RE.findall(summary)
    passed = int(passed_matches[-1]) if passed_matches else 0
    failed_matches = _FAIL_RE.findall(summary)
    failed = int(failed_matches[-1]) if failed_matches else (total - passed)
    rate = passed / total if total else 0.0
    return rate, {
        "reason": "ok",
        "selectors_total": total,
        "selectors_passed": passed,
        "selectors_failed": failed,
        "returncode": proc.returncode,
    }
