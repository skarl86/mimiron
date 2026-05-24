"""bench run 흐름 (similarity_provider 없이 deferred 반환 확인)."""
import json
import shutil
import subprocess
from pathlib import Path
import pytest


@pytest.fixture
def bench_project(tmp_path: Path) -> Path:
    """benchmarks/B00-toy 가 있는 가짜 프로젝트."""
    fixtures = Path(__file__).parent.parent / "fixtures" / "benchmarks" / "B00-toy"
    proj = tmp_path / "proj"
    proj.mkdir()
    shutil.copytree(fixtures, proj / "benchmarks" / "B00-toy")
    (proj / "benchmarks" / "_cutoff.yaml").write_text(
        "schema_version: 1\ncutoff_case: 0.75\ncutoff_global: 0.75\n"
        "w_test: 0.6\nw_sim: 0.4\ncertainty_band: 0.05\n"
    )
    # toy_repo (benchmark.repo가 가리키는)는 가벼운 git 초기화
    toy = proj / "benchmarks" / "B00-toy" / "toy_repo"
    toy.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=toy, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=toy, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=toy, check=True)
    (toy / "a.txt").write_text("v1\n")
    subprocess.run(["git", "add", "."], cwd=toy, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "c1"], cwd=toy, check=True, capture_output=True)
    (toy / "toy.txt").write_text("toy")
    subprocess.run(["git", "add", "."], cwd=toy, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "c2"], cwd=toy, check=True, capture_output=True)
    return proj


def test_bench_run_returns_verdict(bench_project: Path) -> None:
    import shutil as _sh
    bin_path = _sh.which("mimiron-bench") or str(
        (Path(__file__).parent.parent.parent / ".venv" / "bin" / "mimiron-bench").resolve()
    )
    rc = subprocess.run(
        [bin_path, "run", "B00-toy"],
        cwd=bench_project,
        capture_output=True,
        text=True,
        check=False,
    )
    assert rc.returncode in {0, 1}, rc.stderr
    v = json.loads(rc.stdout)
    assert v["id"] == "B00-toy"
    assert "status" in v
    # similarity_provider 없으므로 deferred
    assert v["status"] == "deferred"
    # v0.3.0 #20: deferred mode still measures on target_ref
    assert v["details"]["test_measurement_mode"] == "target-ref"


def _bin_path() -> str:
    import shutil as _sh
    return _sh.which("mimiron-bench") or str(
        (Path(__file__).parent.parent.parent / ".venv" / "bin" / "mimiron-bench").resolve()
    )


def _write_judge_json(path: Path, score: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"score": score, "rationale": f"fixture sim={score}"}))


def _write_candidate_diff(path: Path, content: str) -> None:
    """Per v0.3.0 #20 + #24: per-bench input path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


# v0.3.0 #20 — candidate-applied test measurement + sim_gate verdict


def test_candidate_applied_passes_when_sim_above_gate_and_score_high(
    bench_project: Path,
) -> None:
    """clean candidate + sim >= gate + score >= cutoff → passed."""
    judge_path = bench_project / ".mimiron" / "_outer" / "judge" / "B00-toy.json"
    _write_judge_json(judge_path, score=0.95)
    candidate_path = bench_project / ".mimiron" / "_bench" / "_input" / "B00-toy.diff"
    # B00-toy's base_ref=HEAD~1 has only a.txt; target adds toy.txt. Use the canonical expected diff.
    _write_candidate_diff(
        candidate_path,
        "diff --git a/toy.txt b/toy.txt\nnew file mode 100644\n--- /dev/null\n+++ b/toy.txt\n@@ -0,0 +1 @@\n+toy\n",
    )
    rc = subprocess.run(
        [_bin_path(), "run", "B00-toy", "--similarity-from", str(judge_path)],
        cwd=bench_project,
        capture_output=True,
        text=True,
        check=False,
    )
    assert rc.returncode in {0, 1}, rc.stderr
    v = json.loads(rc.stdout)
    assert v["status"] == "passed"
    assert v["details"]["test_measurement_mode"] == "candidate-applied"
    assert v["details"]["candidate_apply_status"] == "applied"


def test_sim_gate_forces_failed_when_sim_below_threshold(bench_project: Path) -> None:
    """sim < gate must force failed even when bench_score would otherwise pass cutoff.

    sim=0.45 → bench_score = 1.0*0.6 + 0.45*0.4 = 0.78 ≥ 0.75 cutoff
    → without gate this would be 'passed', but gate (0.5) forces 'failed'.
    Exactly the dogfood/005 B02 'test_pass dominance' scenario.
    """
    judge_path = bench_project / ".mimiron" / "_outer" / "judge" / "B00-toy.json"
    _write_judge_json(judge_path, score=0.45)
    candidate_path = bench_project / ".mimiron" / "_bench" / "_input" / "B00-toy.diff"
    _write_candidate_diff(
        candidate_path,
        "diff --git a/toy.txt b/toy.txt\nnew file mode 100644\n--- /dev/null\n+++ b/toy.txt\n@@ -0,0 +1 @@\n+toy\n",
    )
    rc = subprocess.run(
        [_bin_path(), "run", "B00-toy", "--similarity-from", str(judge_path)],
        cwd=bench_project,
        capture_output=True,
        text=True,
        check=False,
    )
    assert rc.returncode in {0, 1}, rc.stderr
    v = json.loads(rc.stdout)
    assert v["status"] == "failed"
    assert v["bench_score"] >= 0.75  # would have passed without gate
    assert v["details"]["sim_gate"] == 0.5


def test_corrupt_candidate_apply_fails_test_pass_zero(bench_project: Path) -> None:
    """corrupt diff (B02 scenario) → apply-failed, test_pass=0, sim still computed."""
    judge_path = bench_project / ".mimiron" / "_outer" / "judge" / "B00-toy.json"
    _write_judge_json(judge_path, score=0.85)  # would pass cutoff but apply fails
    candidate_path = bench_project / ".mimiron" / "_bench" / "_input" / "B00-toy.diff"
    # broken hunk counts — git apply --check will reject
    _write_candidate_diff(
        candidate_path,
        "diff --git a/toy.txt b/toy.txt\n--- a/toy.txt\n+++ b/toy.txt\n@@ -999,3 +999,3 @@\n nonexistent context\n",
    )
    rc = subprocess.run(
        [_bin_path(), "run", "B00-toy", "--similarity-from", str(judge_path)],
        cwd=bench_project,
        capture_output=True,
        text=True,
        check=False,
    )
    assert rc.returncode in {0, 1}, rc.stderr
    v = json.loads(rc.stdout)
    assert v["details"]["candidate_apply_status"] == "apply-failed"
    assert v["test_pass_rate"] == 0.0
    # 0.0 * 0.6 + 0.85 * 0.4 = 0.34 < 0.75 cutoff -> failed (also sim<0.5 would also force fail anyway)
    assert v["status"] == "failed"


def test_missing_candidate_diff_marked_no_candidate(bench_project: Path) -> None:
    """similarity provider set but no candidate diff present → apply_status=no-candidate."""
    judge_path = bench_project / ".mimiron" / "_outer" / "judge" / "B00-toy.json"
    _write_judge_json(judge_path, score=0.9)
    # intentionally do NOT write candidate diff
    rc = subprocess.run(
        [_bin_path(), "run", "B00-toy", "--similarity-from", str(judge_path)],
        cwd=bench_project,
        capture_output=True,
        text=True,
        check=False,
    )
    assert rc.returncode in {0, 1}, rc.stderr
    v = json.loads(rc.stdout)
    assert v["details"]["candidate_apply_status"] == "no-candidate"
    assert v["test_pass_rate"] == 0.0
