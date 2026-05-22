"""mimiron CLI — argparse 기반 결정적 진입점."""
from __future__ import annotations

import argparse
import json as _json
import re
import sys
from pathlib import Path

from mimiron.plan import Plan, PlanError
from mimiron.scanner import scan as run_scan
from mimiron.state import State

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")

EXIT_OK = 0
EXIT_RUNTIME_ERROR = 1
EXIT_USAGE_ERROR = 2


def _sidecar_dir(cwd: Path, slug: str) -> Path:
    return cwd / ".mimiron" / slug


def _check_slug_or_die(slug: str) -> None:
    if not SLUG_RE.match(slug):
        raise SystemExit(
            f"invalid slug {slug!r}: must match {SLUG_RE.pattern} "
            "(lowercase alnum + dashes, max 63 chars, no '..' or path separators)"
        )


def cmd_init(args: argparse.Namespace) -> int:
    _check_slug_or_die(args.slug)
    cwd = Path.cwd()
    sidecar = _sidecar_dir(cwd, args.slug)
    if sidecar.exists():
        print(f"error: slug {args.slug!r} already exists at {sidecar}", file=sys.stderr)
        return EXIT_RUNTIME_ERROR
    sidecar.mkdir(parents=True)
    state = State.create(slug=args.slug, persistent=not args.no_persist)
    state.save(sidecar / "state.json")
    print(f"initialized {args.slug} at {sidecar}")
    return EXIT_OK


def cmd_ls(args: argparse.Namespace) -> int:
    cwd = Path.cwd()
    root = cwd / ".mimiron"
    if not root.exists():
        print("no slugs (no .mimiron directory)")
        return EXIT_OK
    slugs = sorted(p.name for p in root.iterdir() if p.is_dir() and p.name != "_global")
    if not slugs:
        print("no slugs")
        return EXIT_OK
    print(f"{'SLUG':30}  {'PHASE':10}  {'PERSIST':8}")
    for slug in slugs:
        try:
            state = State.load(root / slug / "state.json")
        except (FileNotFoundError, ValueError) as e:
            print(f"{slug:30}  {'corrupted':10}  {'-':8}  ({e})")
            continue
        persist = "yes" if state.persistent else "no"
        print(f"{slug:30}  {state.phase:10}  {persist:8}")
    return EXIT_OK


def cmd_status(args: argparse.Namespace) -> int:
    cwd = Path.cwd()
    state_path = _sidecar_dir(cwd, args.slug) / "state.json"
    if not state_path.exists():
        print(f"error: slug {args.slug!r} not found at {state_path}", file=sys.stderr)
        return EXIT_RUNTIME_ERROR
    state = State.load(state_path)
    persist_tag = "persistent ✓" if state.persistent else "persistent ✗"
    paused_tag = "  [paused]" if state.paused else ""
    print(f"{state.slug}  [{persist_tag}]{paused_tag}")
    print(f"├─ phase:     {state.phase}")
    print(f"├─ retries:   {dict(state.retries) if state.retries else '(none)'}")
    print(
        f"├─ gates:     {len(state.gate_history)} recorded "
        f"(consecutive_fail={state.consecutive_gate_fails})"
    )
    print(f"├─ tokens:    {state.token_usage}")
    print(f"└─ updated:   {state.updated_at}")
    return EXIT_OK


def cmd_scan(args: argparse.Namespace) -> int:
    cwd = Path.cwd()
    sidecar = _sidecar_dir(cwd, args.slug)
    state_path = sidecar / "state.json"
    plan_path = sidecar / "plan.yaml"
    if not state_path.exists():
        print(f"error: slug {args.slug!r} not initialized", file=sys.stderr)
        return EXIT_RUNTIME_ERROR
    if not plan_path.exists():
        print(f"error: plan.yaml not found at {plan_path}", file=sys.stderr)
        return EXIT_RUNTIME_ERROR
    state = State.load(state_path)
    try:
        plan = Plan.load(plan_path)
        plan.validate()
    except PlanError as e:
        print(f"plan invalid: {e}", file=sys.stderr)
        return EXIT_USAGE_ERROR
    result = run_scan(plan, state.completed_task_ids, state.in_flight_task_ids)
    print(
        _json.dumps(
            {
                "slug": args.slug,
                "phase": state.phase,
                "ready": result.ready,
                "in_flight": result.in_flight,
                "pending": result.pending,
                "phase_done": result.phase_done,
            },
            indent=2,
        )
    )
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mimiron")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="initialize a new slug")
    p_init.add_argument("slug")
    p_init.add_argument("--no-persist", action="store_true", help="disable persistent loop")
    p_init.set_defaults(func=cmd_init)

    p_ls = sub.add_parser("ls", help="list all slugs with phase")
    p_ls.set_defaults(func=cmd_ls)

    p_status = sub.add_parser("status", help="show status of a slug")
    p_status.add_argument("slug")
    p_status.set_defaults(func=cmd_status)

    p_scan = sub.add_parser("scan", help="compute next ready tasks")
    p_scan.add_argument("slug")
    p_scan.set_defaults(func=cmd_scan)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        rc = args.func(args)
    except SystemExit as exc:
        msg = str(exc)
        if msg:
            print(msg, file=sys.stderr)
        return EXIT_USAGE_ERROR
    # M3: guard against subcommands that forget to `return`
    return int(rc) if rc is not None else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
