"""swebench_runner — pytest selector 기반 test_pass_rate 측정."""
from __future__ import annotations

import json
from unittest.mock import patch


def _mk_meta(tmp_path, ftp, ptp):
    p = tmp_path / "_swebench.json"
    p.write_text(json.dumps({"FAIL_TO_PASS": ftp, "PASS_TO_PASS": ptp}))
    return p


def test_run_swebench_tests_all_pass_returns_1(tmp_path):
    from mimiron.bench.swebench_runner import run_swebench_tests

    meta = _mk_meta(tmp_path, ftp=["t::a"], ptp=["t::b"])
    fake = type("R", (), {
        "returncode": 0,
        "stdout": "2 passed in 0.1s",
        "stderr": "",
    })()
    with patch("subprocess.run", return_value=fake) as m:
        rate, details = run_swebench_tests(meta_path=meta, repo_root=tmp_path)
    assert rate == 1.0
    assert details["selectors_total"] == 2
    assert details["selectors_passed"] == 2
    args = m.call_args[0][0]
    assert "t::a" in args and "t::b" in args


def test_run_swebench_tests_partial_pass_returns_fraction(tmp_path):
    from mimiron.bench.swebench_runner import run_swebench_tests

    meta = _mk_meta(tmp_path, ftp=["t::a", "t::b"], ptp=["t::c", "t::d"])
    fake = type("R", (), {
        "returncode": 1,
        "stdout": "2 passed, 2 failed in 0.3s",
        "stderr": "",
    })()
    with patch("subprocess.run", return_value=fake):
        rate, details = run_swebench_tests(meta_path=meta, repo_root=tmp_path)
    assert rate == 0.5
    assert details["selectors_passed"] == 2


def test_run_swebench_tests_no_selectors_returns_0(tmp_path):
    from mimiron.bench.swebench_runner import run_swebench_tests

    meta = _mk_meta(tmp_path, ftp=[], ptp=[])
    rate, details = run_swebench_tests(meta_path=meta, repo_root=tmp_path)
    assert rate == 0.0
    assert details["reason"] == "no_selectors"


def test_run_swebench_tests_env_error_returns_0_with_reason(tmp_path):
    from mimiron.bench.swebench_runner import run_swebench_tests

    meta = _mk_meta(tmp_path, ftp=["t::a"], ptp=[])
    fake = type("R", (), {
        "returncode": 2,  # pytest collection error
        "stdout": "",
        "stderr": "ImportError: no module x",
    })()
    with patch("subprocess.run", return_value=fake):
        rate, details = run_swebench_tests(meta_path=meta, repo_root=tmp_path)
    assert rate == 0.0
    assert details["reason"] == "env_error"


def test_run_swebench_tests_ignores_assertion_message_pass_count(tmp_path):
    """Regression: pytest assertion msg like 'expected 5 passed' must NOT be parsed as summary."""
    from mimiron.bench.swebench_runner import run_swebench_tests

    meta = _mk_meta(tmp_path, ftp=["t::a"], ptp=[])
    fake = type("R", (), {
        "returncode": 1,
        "stdout": (
            "FAILED tests/foo.py::test_a - AssertionError: expected 5 passed but got 0\n"
            "1 failed in 0.01s\n"
        ),
        "stderr": "",
    })()
    with patch("subprocess.run", return_value=fake):
        rate, details = run_swebench_tests(meta_path=meta, repo_root=tmp_path)
    assert rate == 0.0, "must not extract '5 passed' from assertion message"
    assert details["selectors_passed"] == 0


def test_run_swebench_tests_timeout_returns_0_with_reason(tmp_path):
    """Coverage: TimeoutExpired path."""
    import subprocess
    from mimiron.bench.swebench_runner import run_swebench_tests

    meta = _mk_meta(tmp_path, ftp=["t::a"], ptp=[])
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["pytest"], timeout=1)):
        rate, details = run_swebench_tests(meta_path=meta, repo_root=tmp_path, timeout_s=1)
    assert rate == 0.0
    assert details["reason"] == "timeout"
    assert details["timeout_s"] == 1
