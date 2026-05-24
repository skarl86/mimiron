"""SWE-bench importer unit tests."""
from __future__ import annotations

from mimiron.bench.swebench_import import (
    InstanceFeatures,
    compute_features,
    stratify_instances,
)


def _mk_inst(iid: str, repo: str, patch: str, ftp: list[str], ptp: list[str]) -> dict:
    return {
        "instance_id": iid,
        "repo": repo,
        "base_commit": "deadbeef",
        "problem_statement": f"issue for {iid}",
        "patch": patch,
        "FAIL_TO_PASS": ftp,
        "PASS_TO_PASS": ptp,
        "version": "1.0",
    }


def test_compute_features_returns_metric_triplet():
    inst = _mk_inst(
        iid="x__x-1",
        repo="x/x",
        patch="diff --git a/foo.py\n+x = 1\n",
        ftp=["tests/test_a.py::ta", "tests/test_a.py::tb"],
        ptp=["tests/test_a.py::tc"],
    )
    f = compute_features(inst)
    assert isinstance(f, InstanceFeatures)
    assert f.patch_bytes == len(inst["patch"])
    assert f.fail_to_pass_count == 2
    assert f.touched_files == 1  # 단일 diff --git 헤더


def test_stratify_balances_difficulty_and_repo_diversity():
    insts = []
    # 12 instances across 3 repos, varying difficulty signals
    for i in range(12):
        insts.append(_mk_inst(
            iid=f"r{i % 3}__r{i % 3}-{i}",
            repo=f"r{i % 3}/r{i % 3}",
            patch="d" * (100 * (i + 1)),  # increasing patch size
            ftp=[f"t::{j}" for j in range(i % 4 + 1)],
            ptp=[],
        ))
    selected = stratify_instances(insts, target=6, seed=42, max_per_repo=2)
    assert len(selected) == 6
    repos = [s["repo"] for s in selected]
    # max_per_repo=2 → no repo appears more than twice
    assert all(repos.count(r) <= 2 for r in set(repos))
    difficulties = [s["_mimiron_difficulty"] for s in selected]
    assert "easy" in difficulties and "hard" in difficulties


def test_stratify_is_deterministic_with_same_seed():
    insts = [_mk_inst(f"a__a-{i}", "a/a", "x" * (i + 1), ["t::x"], []) for i in range(8)]
    a = stratify_instances(insts, target=4, seed=7, max_per_repo=4)
    b = stratify_instances(insts, target=4, seed=7, max_per_repo=4)
    assert [x["instance_id"] for x in a] == [x["instance_id"] for x in b]
