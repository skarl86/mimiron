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


def _swebench_run_setup(tmp_path, monkeypatch):
    """Shared fixture scaffolding for `mimiron-bench run X --swebench-tests` tests.

    Returns (fixture_dir, real_run, selective_run_factory).
    """
    monkeypatch.chdir(tmp_path)
    fixture = tmp_path / "benchmarks" / "SWE-LITE-x"
    fixture.mkdir(parents=True)
    (fixture / "benchmark.yaml").write_text(
        "id: SWE-LITE-x\n"
        f"repo: {tmp_path}\n"
        "base_ref: HEAD\n"
        "target_ref: null\n"
        "issue_text_file: issue.md\n"
        "expected_diff_file: expected.diff\n"
        "test_command: 'pytest -q'\n"
        "difficulty: easy\n"
        "swebench_meta: _swebench.json\n"
    )
    (fixture / "issue.md").write_text("p")
    (fixture / "expected.diff").write_text("d")
    (fixture / "_swebench.json").write_text(
        json.dumps({"FAIL_TO_PASS": ["t::a"], "PASS_TO_PASS": []})
    )

    import subprocess as _sp
    real_run = _sp.run

    # Initialize a real git repo at tmp_path so worktree_iso can clone from it
    _sp.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    _sp.run(["git", "-c", "user.email=t@e", "-c", "user.name=t",
             "commit", "-q", "--allow-empty", "-m", "init"], cwd=tmp_path, check=True)

    def make_selective_run():
        """git worktree calls → real; git apply → fake-success; pytest → fake-passed."""
        def selective_run(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args")
            if isinstance(cmd, list) and cmd and cmd[0] == "git":
                if len(cmd) > 1 and cmd[1] == "apply":
                    # Fake git apply success — candidate diff content doesn't need to be valid
                    return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
                return real_run(*args, **kwargs)
            # Fake pytest result (1 passed)
            return type("R", (), {"returncode": 0, "stdout": "1 passed in 0.01s", "stderr": ""})()
        return selective_run

    monkeypatch.delenv("MIMIRON_BENCH_DRY_RUN", raising=False)
    return fixture, real_run, make_selective_run


def test_bench_run_with_swebench_tests_flag_uses_runner(tmp_path, monkeypatch):
    """`mimiron-bench run X --swebench-tests` + candidate diff → resolved=True, status=passed, rc=0."""
    from mimiron.bench import cli as bench_cli

    _, _, make_selective_run = _swebench_run_setup(tmp_path, monkeypatch)

    # Provide a candidate diff at the preferred per-bench path so _find_candidate_diff hits it.
    work_root = tmp_path / ".mimiron" / "_bench"
    (work_root / "_input").mkdir(parents=True)
    (work_root / "_input" / "SWE-LITE-x.diff").write_text("dummy diff content\n")

    with patch("subprocess.run", side_effect=make_selective_run()):
        rc = bench_cli.main(["run", "SWE-LITE-x", "--swebench-tests"])
    assert rc == 0
    status_file = tmp_path / ".mimiron" / "_outer" / "status" / "SWE-LITE-x.json"
    assert status_file.exists()
    v = json.loads(status_file.read_text())
    assert v["test_pass_rate"] == 1.0
    assert v["bench_score"] == 1.0
    assert v["status"] == "passed"
    assert v["details"]["resolved"] is True
    assert v["details"]["apply_status"] == "applied"
    assert v["details"]["candidate_found"] is True


def test_bench_run_swebench_tests_no_candidate_records_apply_status(tmp_path, monkeypatch):
    """When candidate diff is missing, apply_status='no_candidate' and bench_score falls back to rate."""
    from mimiron.bench import cli as bench_cli

    _, _, make_selective_run = _swebench_run_setup(tmp_path, monkeypatch)

    # No candidate diff written this time.
    with patch("subprocess.run", side_effect=make_selective_run()):
        rc = bench_cli.main(["run", "SWE-LITE-x", "--swebench-tests"])
    # rate=1.0 (pytest faked), no sim_provider, score=rate=1.0, resolved=True → status=passed → rc=0
    assert rc == 0
    status_file = tmp_path / ".mimiron" / "_outer" / "status" / "SWE-LITE-x.json"
    v = json.loads(status_file.read_text())
    assert v["details"]["apply_status"] == "no_candidate"
    assert v["details"]["candidate_found"] is False
    assert v["test_pass_rate"] == 1.0
    assert v["bench_score"] == 1.0
