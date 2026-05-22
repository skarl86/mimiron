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
        print(f"error: benchmark {args.id!r} not found at {bench_dir}", file=sys.stderr)
        return 2
    try:
        b = Benchmark.load(bench_dir / "benchmark.yaml")
    except BenchmarkError as e:
        print(f"benchmark invalid: {e}", file=sys.stderr)
        return 3
    if os.environ.get("MIMIRON_BENCH_DRY_RUN") == "1":
        result = {"id": b.id, "status": "deferred", "reason": "dry-run mode"}
        print(json.dumps(result, indent=2))
        return 0
    print(json.dumps({"id": b.id, "status": "pending", "reason": "runner not implemented yet"}))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mimiron-bench")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list")
    p_list.set_defaults(func=cmd_list)

    p_run = sub.add_parser("run")
    p_run.add_argument("id")
    p_run.set_defaults(func=cmd_run)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
