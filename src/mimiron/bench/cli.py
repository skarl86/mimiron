"""mimiron-bench — outer-loop self-evaluation CLI."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from mimiron.bench.runner import Benchmark, BenchmarkError


def _benchmark_dirs(cwd: Path) -> list[Path]:
    root = cwd / "benchmarks"
    if not root.exists():
        return []
    return sorted(
        p for p in root.iterdir() if p.is_dir() and (p / "benchmark.yaml").exists()
    )


def cmd_list(args: argparse.Namespace) -> int:
    cwd = Path.cwd()
    dirs = _benchmark_dirs(cwd)
    if not dirs:
        print("no benchmarks (looked for benchmarks/<id>/benchmark.yaml)")
        return 0
    print(f"{'ID':30}  {'DIFFICULTY':10}  STATUS")
    for d in dirs:
        try:
            b = Benchmark.load(d / "benchmark.yaml")
        except BenchmarkError as e:
            print(f"{d.name:30}  {'corrupted':10}  ({e})")
            continue
        status_path = cwd / ".mimiron" / "_outer" / "status" / f"{b.id}.json"
        status = "pending"
        if status_path.exists():
            status = json.loads(status_path.read_text())["status"]
        print(f"{b.id:30}  {b.difficulty:10}  {status}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    cwd = Path.cwd()
    bench_dir = cwd / "benchmarks" / args.id
    if not (bench_dir / "benchmark.yaml").exists():
        print(f"error: benchmark {args.id!r} not found", file=sys.stderr)
        return 2
    b = Benchmark.load(bench_dir / "benchmark.yaml")
    if os.environ.get("MIMIRON_BENCH_DRY_RUN") == "1":
        print(json.dumps({"id": b.id, "status": "deferred", "reason": "dry-run"}))
        return 0
    similarity_provider = None
    judge_path_str = getattr(args, "similarity_from", None)
    if judge_path_str:
        from mimiron.bench.judge import JudgeError, load_similarity_from_file
        judge_path = Path(judge_path_str)
        if not judge_path.is_absolute():
            judge_path = (cwd / judge_path).resolve()
        try:
            similarity_provider = load_similarity_from_file(judge_path)
        except (JudgeError, FileNotFoundError) as e:
            print(f"error: judge file: {e}", file=sys.stderr)
            return 2
    work_root = cwd / ".mimiron" / "_bench"
    work_root.mkdir(parents=True, exist_ok=True)
    try:
        from mimiron.bench.runner import run_benchmark
        v = run_benchmark(
            benchmark=b,
            work_root=work_root,
            similarity_provider=similarity_provider,
        )
    except Exception as e:
        print(json.dumps({"id": b.id, "status": "failed", "error": str(e)}))
        return 4
    status_dir = cwd / ".mimiron" / "_outer" / "status"
    status_dir.mkdir(parents=True, exist_ok=True)
    (status_dir / f"{b.id}.json").write_text(json.dumps(dict(v), indent=2))
    print(json.dumps(dict(v), indent=2))
    return 0 if v["status"] != "failed" else 1


def cmd_compare(args: argparse.Namespace) -> int:
    cwd = Path.cwd()
    s1 = cwd / args.dir1
    s2 = cwd / args.dir2
    if not s1.exists() or not s2.exists():
        print("error: directories must both exist", file=sys.stderr)
        return 2
    ids = sorted({p.stem for p in s1.glob("*.json")} | {p.stem for p in s2.glob("*.json")})
    print(f"{'ID':30}  {'OLD':10}  {'NEW':10}  DIFF")
    for bid in ids:
        old_path = s1 / f"{bid}.json"
        new_path = s2 / f"{bid}.json"
        old = json.loads(old_path.read_text())["bench_score"] if old_path.exists() else None
        new = json.loads(new_path.read_text())["bench_score"] if new_path.exists() else None
        old_s = f"{old:.3f}" if old is not None else "  -"
        new_s = f"{new:.3f}" if new is not None else "  -"
        diff_s = f"{new - old:+.3f}" if (old is not None and new is not None) else "  -"
        print(f"{bid:30}  {old_s:10}  {new_s:10}  {diff_s}")
    return 0


def cmd_suite(args: argparse.Namespace) -> int:
    """v0: list와 동일 출력 + aggregate placeholder."""
    cwd = Path.cwd()
    dirs = _benchmark_dirs(cwd)
    scores: list[float] = []
    for d in dirs:
        b = Benchmark.load(d / "benchmark.yaml")
        status_path = cwd / ".mimiron" / "_outer" / "status" / f"{b.id}.json"
        if status_path.exists():
            v = json.loads(status_path.read_text())
            if v.get("bench_score") is not None:
                scores.append(v["bench_score"])
    agg = sum(scores) / len(scores) if scores else None
    print(
        json.dumps(
            {
                "benchmarks": len(dirs),
                "scored": len(scores),
                "suite_aggregate": agg,
            },
            indent=2,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mimiron-bench")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list")
    p_list.set_defaults(func=cmd_list)

    p_run = sub.add_parser("run")
    p_run.add_argument("id")
    p_run.add_argument(
        "--similarity-from",
        dest="similarity_from",
        default=None,
        help="외부에서 미리 산출한 judge JSON 경로 (score+rationale).",
    )
    p_run.set_defaults(func=cmd_run)

    p_cmp = sub.add_parser("compare")
    p_cmp.add_argument("dir1")
    p_cmp.add_argument("dir2")
    p_cmp.set_defaults(func=cmd_compare)

    p_suite = sub.add_parser("suite")
    p_suite.set_defaults(func=cmd_suite)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
