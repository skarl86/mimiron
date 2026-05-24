#!/usr/bin/env python3
"""Self-contained Python launcher for mimiron CLI wrappers.

Clears PYTHONPATH from env so subprocesses don't inherit, manages sys.path
explicitly using CLAUDE_PLUGIN_ROOT (Claude Code) or fallback to script's
grandparent directory.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv
    if len(argv) < 2:
        print("usage: _launcher.py {mimiron|mimiron-bench} <args>...", file=sys.stderr)
        return 2
    entrypoint = argv[1]
    # Forward remaining args to the chosen CLI via sys.argv mutation.
    sys.argv = [entrypoint, *argv[2:]]

    # 1) Clear PYTHONPATH so subprocess (pytest/ruff/mypy) won't inherit.
    os.environ.pop("PYTHONPATH", None)

    # 2) Determine plugin root.
    env_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env_root:
        plugin_root = Path(env_root)
    else:
        # Fallback: launcher's grandparent (scripts/_launcher.py -> plugin root)
        plugin_root = Path(__file__).resolve().parent.parent

    # 3) Make `mimiron` importable.
    src_path = str(plugin_root / "src")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)

    # 4) Dispatch.
    if entrypoint == "mimiron":
        from mimiron.cli import main as cli_main  # type: ignore[import-not-found]
        return cli_main()
    elif entrypoint == "mimiron-bench":
        from mimiron.bench.cli import main as bench_main  # type: ignore[import-not-found]
        return bench_main()
    else:
        print(f"error: unknown entrypoint {entrypoint!r}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
