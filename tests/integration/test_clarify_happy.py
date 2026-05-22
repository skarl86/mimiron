"""A4 졸업: stub clarification.md → ambiguity gate pass."""
import shutil
import subprocess
from pathlib import Path


MIMIRON_BIN = shutil.which("mimiron") or str(
    (Path(__file__).parent.parent.parent / ".venv" / "bin" / "mimiron").resolve()
)


CLARIFY_FIXTURE = """---
slug: hello
ambiguity_score: 0.12
samples: [0.10, 0.12, 0.14]
---

# Clarification — hello

## Goal
사용자가 입력한 짧은 feature를 명확화

## Resolved
- acceptance criteria: 명세된 endpoint 존재
- domain terms: 모두 정의됨
- boundary: 인증 미포함
"""


def test_clarify_to_ambiguity_gate_pass(tmp_path: Path) -> None:
    subprocess.run([MIMIRON_BIN, "init", "hello"], cwd=tmp_path, check=True)
    sidecar = tmp_path / ".mimiron" / "hello"
    (sidecar / "clarification.md").write_text(CLARIFY_FIXTURE)
    rc = subprocess.run(
        [MIMIRON_BIN, "gate", "hello", "ambiguity"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert rc.returncode == 0, rc.stderr
    assert "pass" in rc.stdout
