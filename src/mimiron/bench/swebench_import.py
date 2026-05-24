"""SWE-bench Lite → mimiron fixture importer."""
from __future__ import annotations

import json as _json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mimiron import yaml_compat as yaml


class ImportError(ValueError):  # noqa: A001 — intentional module-scope shadow of builtin
    """SWE-bench import 오류."""


@dataclass(frozen=True)
class InstanceFeatures:
    patch_bytes: int
    fail_to_pass_count: int
    touched_files: int

    def difficulty_score(self) -> float:
        # 가중치: file > test > patch size (§8 spec)
        return self.patch_bytes + 2 * self.fail_to_pass_count + 3 * self.touched_files


def compute_features(instance: dict[str, Any]) -> InstanceFeatures:
    patch = instance.get("patch", "") or ""
    files = sum(1 for line in patch.splitlines() if line.startswith("diff --git"))
    return InstanceFeatures(
        patch_bytes=len(patch),
        fail_to_pass_count=len(instance.get("FAIL_TO_PASS", []) or []),
        touched_files=max(files, 1),
    )


def _classify(scores: list[float], score: float) -> str:
    """quantile-based difficulty label."""
    sorted_scores = sorted(scores)
    n = len(sorted_scores)
    if n == 0:
        return "medium"
    idx = sorted_scores.index(score)
    if idx < n / 3:
        return "easy"
    if idx < 2 * n / 3:
        return "medium"
    return "hard"


def stratify_instances(
    instances: list[dict[str, Any]],
    *,
    target: int,
    seed: int,
    max_per_repo: int = 4,
) -> list[dict[str, Any]]:
    """Difficulty quantile + repo diversity. 결정적."""
    if not instances:
        return []
    rng = random.Random(seed)
    scored = [(inst, compute_features(inst).difficulty_score()) for inst in instances]
    all_scores = [s for _, s in scored]

    for inst, score in scored:
        inst["_mimiron_difficulty"] = _classify(all_scores, score)

    buckets: dict[str, list[dict]] = {"easy": [], "medium": [], "hard": []}
    for inst, _ in scored:
        buckets[inst["_mimiron_difficulty"]].append(inst)

    for b in buckets.values():
        rng.shuffle(b)

    quota_easy = (target + 2) // 3      # 7 if target=20
    quota_medium = (target + 1) // 3    # 7 if target=20
    quota_hard = target - quota_easy - quota_medium  # 6 if target=20

    selected: list[dict] = []
    per_repo: dict[str, int] = {}

    def _pick_from(bucket: list[dict], quota: int) -> int:
        taken = 0
        for inst in bucket:
            if taken >= quota:
                break
            repo = inst["repo"]
            if per_repo.get(repo, 0) >= max_per_repo:
                continue
            selected.append(inst)
            per_repo[repo] = per_repo.get(repo, 0) + 1
            taken += 1
        return taken

    _pick_from(buckets["easy"], quota_easy)
    _pick_from(buckets["medium"], quota_medium)
    _pick_from(buckets["hard"], quota_hard)

    # 부족분 (max_per_repo 로 인해 quota 못 채운 경우) — 다른 bucket 에서 보충
    if len(selected) < target:
        leftover = [i for b in buckets.values() for i in b if i not in selected]
        rng.shuffle(leftover)
        for inst in leftover:
            if len(selected) >= target:
                break
            repo = inst["repo"]
            if per_repo.get(repo, 0) >= max_per_repo:
                continue
            selected.append(inst)
            per_repo[repo] = per_repo.get(repo, 0) + 1

    return selected[:target]


def write_fixture(
    instance: dict[str, Any],
    *,
    root: Path,
    clone_root: str,
) -> Path:
    """SWE-bench instance → benchmarks/SWE-LITE-<id>/ 디렉토리 생성.

    root: benchmarks/ 디렉토리의 부모 (보통 cwd) — 안에 benchmarks/SWE-LITE-XX/ 작성
    clone_root: benchmark.yaml 의 repo 필드가 가리킬 상대 경로 (importer 가 미리 clone)
    """
    iid = instance["instance_id"]
    fixture_id = f"SWE-LITE-{iid}"
    fixture_dir = root / fixture_id
    fixture_dir.mkdir(parents=True, exist_ok=True)

    repo_dir_name = iid.split("__")[0] + "__" + iid.rsplit("-", 1)[0].split("__", 1)[1]
    repo_path = f"{clone_root}/{repo_dir_name}"

    ftp = instance.get("FAIL_TO_PASS", []) or []
    ptp = instance.get("PASS_TO_PASS", []) or []
    selectors = " ".join(ftp + ptp)

    bench_yaml = {
        "id": fixture_id,
        "repo": repo_path,
        "base_ref": instance["base_commit"],
        "target_ref": None,
        "issue_text_file": "issue.md",
        "expected_diff_file": "expected.diff",
        "test_command": f"pytest {selectors} -q",
        "difficulty": instance.get("_mimiron_difficulty", "unknown"),
        "swebench_meta": "_swebench.json",
        "notes": (
            f"Imported from princeton-nlp/SWE-bench_Lite\n"
            f"Original instance_id: {iid}\n"
        ),
    }
    (fixture_dir / "benchmark.yaml").write_text(
        yaml.safe_dump(bench_yaml, sort_keys=False), encoding="utf-8"
    )
    (fixture_dir / "issue.md").write_text(instance["problem_statement"], encoding="utf-8")
    (fixture_dir / "expected.diff").write_text(instance["patch"], encoding="utf-8")

    meta = {
        "instance_id": iid,
        "FAIL_TO_PASS": ftp,
        "PASS_TO_PASS": ptp,
        "version": instance.get("version", "unknown"),
        "environment_setup_commit": instance.get("environment_setup_commit"),
    }
    (fixture_dir / "_swebench.json").write_text(
        _json.dumps(meta, indent=2), encoding="utf-8"
    )

    return fixture_dir


_REQUIRED = ("instance_id", "repo", "base_commit", "problem_statement", "patch")


def load_from_jsonl(path: Path) -> list[dict[str, Any]]:
    """로컬 JSONL → instance dict 리스트. HF 의존성 없음."""
    out: list[dict[str, Any]] = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            rec = _json.loads(line)
        except _json.JSONDecodeError as e:
            raise ImportError(f"line {n}: invalid JSON: {e}") from e
        missing = [k for k in _REQUIRED if k not in rec]
        if missing:
            raise ImportError(f"line {n}: missing required fields {missing}")
        out.append(rec)
    return out


def load_from_huggingface(subset: str = "test") -> list[dict[str, Any]]:
    """HF datasets 의존성 lazy import. PoC 외 사용자가 직접 부를 때만."""
    try:
        from datasets import load_dataset  # type: ignore[import-not-found]
    except ModuleNotFoundError as e:
        raise ImportError(
            "HuggingFace `datasets` not installed. "
            "Install: `uv pip install -e '.[swebench]'` or use --from-jsonl <path>"
        ) from e
    ds = load_dataset("princeton-nlp/SWE-bench_Lite", split=subset)
    return [dict(x) for x in ds]
