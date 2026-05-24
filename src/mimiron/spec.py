"""spec.yaml — clarify·spec phase의 산출."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from mimiron import SCHEMA_VERSION
from mimiron import yaml_compat as yaml
from mimiron.hash_util import sha256_text


class SpecError(ValueError):
    """Spec validation failure."""


VALID_VERIFY_KINDS = frozenset({"test", "grep", "reviewer"})
VALID_CONSTRAINT_KINDS = frozenset({"what", "prescribed_implementation"})


@dataclass
class Verify:
    kind: str
    command: str | None = None
    pattern: str | None = None
    in_: str | None = None  # 'in'은 예약어

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"kind": self.kind}
        if self.command is not None:
            d["command"] = self.command
        if self.pattern is not None:
            d["pattern"] = self.pattern
        if self.in_ is not None:
            d["in"] = self.in_
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Verify":
        return cls(
            kind=d.get("kind", "reviewer"),
            command=d.get("command"),
            pattern=d.get("pattern"),
            in_=d.get("in"),
        )


@dataclass
class Constraint:
    id: str
    desc: str
    kind: str = "what"

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "desc": self.desc, "kind": self.kind}


@dataclass
class AcceptanceCriterion:
    id: str
    desc: str
    verify: Verify

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "desc": self.desc, "verify": self.verify.to_dict()}


@dataclass
class Hypothesis:
    id: str
    claim: str
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Spec:
    schema_version: int
    slug: str
    goal: str
    constraints: list[Constraint]
    acceptance_criteria: list[AcceptanceCriterion]
    ontology: dict[str, Any]
    hypothesis: list[Hypothesis]
    quality_score: float | None
    ambiguity_score: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "slug": self.slug,
            "goal": self.goal,
            "constraints": [c.to_dict() for c in self.constraints],
            "acceptance_criteria": [a.to_dict() for a in self.acceptance_criteria],
            "ontology": self.ontology,
            "hypothesis": [h.to_dict() for h in self.hypothesis],
            "quality_score": self.quality_score,
            "ambiguity_score": self.ambiguity_score,
        }

    @classmethod
    def load(cls, path: Path) -> "Spec":
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        sv = raw.get("schema_version")
        if sv != SCHEMA_VERSION:
            raise SpecError(f"schema_version mismatch: {sv}")
        return cls(
            schema_version=sv,
            slug=raw["slug"],
            goal=raw["goal"],
            constraints=[Constraint(**c) for c in raw.get("constraints", [])],
            acceptance_criteria=[
                AcceptanceCriterion(
                    id=a["id"], desc=a["desc"], verify=Verify.from_dict(a["verify"])
                )
                for a in raw.get("acceptance_criteria", [])
            ],
            ontology=raw.get("ontology") or {},
            hypothesis=[Hypothesis(**h) for h in raw.get("hypothesis", [])],
            quality_score=raw.get("quality_score"),
            ambiguity_score=raw.get("ambiguity_score"),
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.safe_dump(self.to_dict(), allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

    def validate(self) -> None:
        for ac in self.acceptance_criteria:
            if ac.verify.kind not in VALID_VERIFY_KINDS:
                raise SpecError(f"AC {ac.id}: invalid verify.kind {ac.verify.kind!r}")
            if ac.verify.kind == "test" and not ac.verify.command:
                raise SpecError(f"AC {ac.id}: verify.kind=test requires command")
            if ac.verify.kind == "grep" and not (ac.verify.pattern and ac.verify.in_):
                raise SpecError(f"AC {ac.id}: verify.kind=grep requires pattern+in")
        for c in self.constraints:
            if c.kind not in VALID_CONSTRAINT_KINDS:
                raise SpecError(f"constraint {c.id}: invalid kind {c.kind!r}")

    @staticmethod
    def compute_hash(path: Path) -> str:
        return sha256_text(path.read_text(encoding="utf-8"))
