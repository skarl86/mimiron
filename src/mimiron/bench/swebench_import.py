"""SWE-bench Lite → mimiron fixture importer."""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any


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
