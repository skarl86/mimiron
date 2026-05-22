"""mimiron CLI — argparse 기반 결정적 진입점."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

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


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mimiron")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="initialize a new slug")
    p_init.add_argument("slug")
    p_init.add_argument("--no-persist", action="store_true", help="disable persistent loop")
    p_init.set_defaults(func=cmd_init)

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
