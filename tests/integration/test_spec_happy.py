"""A5 졸업: clarify → spec → quality gate pass → phase=plan, spec_hash set."""
import json
import shutil
import subprocess
import yaml
from pathlib import Path


MIMIRON_BIN = shutil.which("mimiron") or str(
    (Path(__file__).parent.parent.parent / ".venv" / "bin" / "mimiron").resolve()
)


def test_full_a4_a5_flow(tmp_path: Path) -> None:
    subprocess.run([MIMIRON_BIN, "init", "demo"], cwd=tmp_path, check=True)
    sidecar = tmp_path / ".mimiron" / "demo"
    (sidecar / "clarification.md").write_text(
        "---\nslug: demo\nambiguity_score: 0.10\nsamples: [0.08, 0.10, 0.12]\n---\n# x\n"
    )
    rc = subprocess.run(
        [MIMIRON_BIN, "gate", "demo", "ambiguity"], cwd=tmp_path, check=False
    )
    assert rc.returncode == 0

    (sidecar / "spec.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": 1, "slug": "demo", "goal": "g",
                "constraints": [],
                "acceptance_criteria": [
                    {
                        "id": "AC01", "desc": "/version returns 200",
                        "verify": {"kind": "test", "command": "echo pass"},
                    }
                ],
                "ontology": {}, "hypothesis": [],
                "quality_score": 0.92, "ambiguity_score": 0.10,
            }
        )
    )
    (sidecar / "quality.samples.json").write_text("[0.90, 0.92, 0.94]")
    rc = subprocess.run(
        [MIMIRON_BIN, "gate", "demo", "quality"], cwd=tmp_path, check=False
    )
    assert rc.returncode == 0

    state = json.loads((sidecar / "state.json").read_text())
    assert state["phase"] == "plan"
    assert state["spec_hash"] is not None
