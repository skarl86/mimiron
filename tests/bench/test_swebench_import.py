"""SWE-bench importer unit tests."""
from __future__ import annotations

from pathlib import Path

import pytest

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


def test_write_fixture_creates_yaml_issue_diff_meta(tmp_path):
    from mimiron.bench.swebench_import import write_fixture

    inst = {
        "instance_id": "django__django-11099",
        "repo": "django/django",
        "base_commit": "419a78300f7c",
        "problem_statement": "Allow non-ASCII username validation",
        "patch": "diff --git a/django/x.py b/django/x.py\n+pass\n",
        "FAIL_TO_PASS": ["tests/auth_tests.py::test_unicode"],
        "PASS_TO_PASS": ["tests/auth_tests.py::test_ascii"],
        "version": "3.0",
        "_mimiron_difficulty": "medium",
    }
    fixture_dir = tmp_path / "benchmarks"
    written = write_fixture(inst, root=fixture_dir, clone_root="../../.bench-clones/swebench")
    assert written.name == "SWE-LITE-django__django-11099"
    assert (written / "benchmark.yaml").exists()
    assert (written / "issue.md").read_text() == "Allow non-ASCII username validation"
    assert (written / "expected.diff").read_text() == inst["patch"]
    import json as _j
    meta = _j.loads((written / "_swebench.json").read_text())
    assert meta["FAIL_TO_PASS"] == ["tests/auth_tests.py::test_unicode"]
    assert meta["instance_id"] == "django__django-11099"


def test_write_fixture_benchmark_yaml_has_swebench_meta_field(tmp_path):
    from mimiron.bench.swebench_import import write_fixture
    from mimiron import yaml_compat as yaml

    inst = {
        "instance_id": "x__x-1", "repo": "x/x", "base_commit": "deadbeef",
        "problem_statement": "p", "patch": "d",
        "FAIL_TO_PASS": ["a::b"], "PASS_TO_PASS": [],
        "version": "1.0", "_mimiron_difficulty": "easy",
    }
    written = write_fixture(inst, root=tmp_path, clone_root="../../.clones")
    y = yaml.safe_load((written / "benchmark.yaml").read_text())
    assert y["swebench_meta"] == "_swebench.json"
    assert y["target_ref"] is None
    assert "pytest" in y["test_command"]
    assert "a::b" in y["test_command"]


def test_write_fixture_handles_hyphenated_org_name(tmp_path):
    """Regression: sphinx-doc__sphinx-9000 must produce 'sphinx-doc__sphinx' repo dir."""
    from mimiron.bench.swebench_import import write_fixture
    from mimiron import yaml_compat as yaml

    inst = {
        "instance_id": "sphinx-doc__sphinx-9000",
        "repo": "sphinx-doc/sphinx", "base_commit": "abc",
        "problem_statement": "p", "patch": "d",
        "FAIL_TO_PASS": ["t::a"], "PASS_TO_PASS": [],
        "version": "1.0", "_mimiron_difficulty": "easy",
    }
    written = write_fixture(inst, root=tmp_path, clone_root="../../.clones")
    assert written.name == "SWE-LITE-sphinx-doc__sphinx-9000"
    y = yaml.safe_load((written / "benchmark.yaml").read_text())
    assert y["repo"] == "../../.clones/sphinx-doc__sphinx"


def test_load_from_jsonl_reads_all_records():
    from mimiron.bench.swebench_import import load_from_jsonl
    p = Path(__file__).parent.parent / "fixtures" / "swebench_sample.jsonl"
    insts = load_from_jsonl(p)
    assert len(insts) == 3
    assert insts[0]["instance_id"] == "django__django-11099"
    assert insts[2]["repo"] == "astropy/astropy"


def test_load_from_jsonl_raises_on_missing_required_field(tmp_path):
    from mimiron.bench.swebench_import import load_from_jsonl, ImportError as IE
    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"instance_id": "x"}\n', encoding="utf-8")
    with pytest.raises(IE):
        load_from_jsonl(bad)


def test_load_from_jsonl_deserializes_json_string_selector_fields(tmp_path):
    """Regression: HF SWE-bench Lite stores FAIL_TO_PASS/PASS_TO_PASS as JSON strings.
    Without normalization write_fixture iterates the str into chars."""
    import json as _j
    from mimiron.bench.swebench_import import load_from_jsonl

    src = tmp_path / "hf_like.jsonl"
    rec = {
        "instance_id": "x__x-1", "repo": "x/x", "base_commit": "c",
        "problem_statement": "p", "patch": "d",
        "FAIL_TO_PASS": '["tests/a.py::test_x", "tests/a.py::test_y[param-1]"]',
        "PASS_TO_PASS": '["tests/a.py::test_z"]',
        "version": "1.0",
    }
    src.write_text(_j.dumps(rec) + "\n", encoding="utf-8")
    insts = load_from_jsonl(src)
    assert insts[0]["FAIL_TO_PASS"] == ["tests/a.py::test_x", "tests/a.py::test_y[param-1]"]
    assert insts[0]["PASS_TO_PASS"] == ["tests/a.py::test_z"]


def test_load_from_jsonl_preserves_list_selector_fields(tmp_path):
    """Backward-compat: if fields are already lists, normalize must be a no-op."""
    import json as _j
    from mimiron.bench.swebench_import import load_from_jsonl

    src = tmp_path / "already_list.jsonl"
    rec = {
        "instance_id": "x__x-1", "repo": "x/x", "base_commit": "c",
        "problem_statement": "p", "patch": "d",
        "FAIL_TO_PASS": ["t::a", "t::b"],
        "PASS_TO_PASS": ["t::c"],
        "version": "1.0",
    }
    src.write_text(_j.dumps(rec) + "\n", encoding="utf-8")
    insts = load_from_jsonl(src)
    assert insts[0]["FAIL_TO_PASS"] == ["t::a", "t::b"]
    assert insts[0]["PASS_TO_PASS"] == ["t::c"]
