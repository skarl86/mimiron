"""게이트 러너들. CLI가 호출, LLM 호출 없는 결정적 게이트만 여기."""
from __future__ import annotations

import shlex
import subprocess
import tomllib
from pathlib import Path
from typing import Any

from mimiron.verdict import Verdict


def run_mechanical_gate(
    *, toml_path: Path, slug: str, cwd: Path, phase: str = "evaluate"
) -> Verdict:
    if not toml_path.exists():
        return Verdict.make(
            slug=slug,
            phase=phase,
            kind="mechanical",
            verdict="fail",
            details={"error": f"mechanical.toml missing at {toml_path}"},
        )
    spec = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    checks: list[dict[str, Any]] = spec.get("checks", [])
    results: list[dict[str, Any]] = []
    overall_pass = True
    for c in checks:
        name = c.get("name", c.get("command", "?"))
        cmd = c["command"]
        timeout = int(c.get("timeout_s", 60))
        try:
            proc = subprocess.run(
                shlex.split(cmd) if isinstance(cmd, str) else cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            rc = proc.returncode
            results.append(
                {
                    "name": name,
                    "command": cmd,
                    "exit_code": rc,
                    "stdout_tail": proc.stdout[-500:],
                    "stderr_tail": proc.stderr[-500:],
                }
            )
            if rc != 0:
                overall_pass = False
        except subprocess.TimeoutExpired:
            overall_pass = False
            results.append({"name": name, "command": cmd, "exit_code": -1, "error": "timeout"})
    return Verdict.make(
        slug=slug,
        phase=phase,
        kind="mechanical",
        verdict="pass" if overall_pass else "fail",
        details={"checks": results},
    )
