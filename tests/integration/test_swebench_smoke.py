"""SWE-bench adapter end-to-end smoke — importer → fixture → run path.

Mimiron pipeline 자체는 mock (LLM 호출 회피). 어댑터 부분만 진짜 코드 경로 검증.
"""
from __future__ import annotations

import json
import subprocess as _sp
from pathlib import Path
from unittest.mock import patch


def test_swebench_end_to_end_importer_to_runner(tmp_path, monkeypatch):
    from mimiron import yaml_compat as yaml
    from mimiron.bench import cli as bench_cli

    monkeypatch.chdir(tmp_path)
    src = Path(__file__).parent.parent / "fixtures" / "swebench_sample.jsonl"

    # 1. Import: 3 instances → 3 fixtures
    rc = bench_cli.main([
        "swebench", "import",
        "--from-jsonl", str(src),
        "--stratified", "3",
        "--seed", "42",
        "--clone-root", str(tmp_path / ".bench-clones"),
    ])
    assert rc == 0
    fixtures = sorted((tmp_path / "benchmarks").glob("SWE-LITE-*"))
    assert len(fixtures) == 3
    # Each fixture has the expected structure
    for f in fixtures:
        assert (f / "benchmark.yaml").exists()
        assert (f / "issue.md").exists()
        assert (f / "expected.diff").exists()
        assert (f / "_swebench.json").exists()

    # 2. Pick one fixture for the run-path test; rewire its benchmark.yaml's repo
    #    to a real git-init'd dir at tmp_path/fake_repo (so isolate_at_ref succeeds).
    target = fixtures[0]
    fake_repo = tmp_path / "fake_repo"
    fake_repo.mkdir()
    _sp.run(["git", "init", "-q", "-b", "main"], cwd=fake_repo, check=True)
    _sp.run(
        ["git", "-c", "user.email=t@e", "-c", "user.name=t",
         "commit", "-q", "--allow-empty", "-m", "init"],
        cwd=fake_repo, check=True,
    )

    y = yaml.safe_load((target / "benchmark.yaml").read_text())
    y["repo"] = str(fake_repo)
    y["base_ref"] = "HEAD"
    (target / "benchmark.yaml").write_text(yaml.safe_dump(y, sort_keys=False))

    # 3. Provide a candidate diff at the location T7's _find_candidate_diff expects:
    #    .mimiron/_bench/_input/<bench_id>.diff (first-priority lookup path).
    #    A minimal valid no-op patch that creates an empty new file — git apply accepts.
    candidate_dir = tmp_path / ".mimiron" / "_bench" / "_input"
    candidate_dir.mkdir(parents=True)
    (candidate_dir / f"{target.name}.diff").write_text(
        "diff --git a/_smoke.txt b/_smoke.txt\n"
        "new file mode 100644\n"
        "index 0000000..e69de29\n"
    )

    # 4. Mock subprocess.run so pytest call returns "1 passed", but git calls pass through.
    real_run = _sp.run

    def selective_run(*args, **kwargs):
        cmd = args[0] if args else (kwargs.get("cmd") or kwargs.get("args"))
        if isinstance(cmd, list) and cmd and cmd[0] == "git":
            return real_run(*args, **kwargs)
        # Fake pytest result — 1 selector (FAIL_TO_PASS=["t::a"]) → rate=1.0
        return type("R", (), {"returncode": 0, "stdout": "1 passed in 0.01s", "stderr": ""})()

    with patch("subprocess.run", side_effect=selective_run):
        monkeypatch.delenv("MIMIRON_BENCH_DRY_RUN", raising=False)
        rc = bench_cli.main(["run", target.name, "--swebench-tests"])

    assert rc == 0  # passed verdict (rate=1.0, no sim_provider → score=1.0, resolved=True)

    # 5. Verify status file shape
    status = tmp_path / ".mimiron" / "_outer" / "status" / f"{target.name}.json"
    assert status.exists()
    v = json.loads(status.read_text())
    assert v["status"] == "passed"
    assert v["test_pass_rate"] == 1.0
    assert v["bench_score"] == 1.0
    assert v["details"]["resolved"] is True
    assert v["details"]["candidate_found"] is True
    assert v["details"]["apply_status"] == "applied"
