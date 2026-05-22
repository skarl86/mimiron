"""spec.yaml 모델."""
from pathlib import Path
import pytest
from mimiron.spec import Spec, SpecError, AcceptanceCriterion, Verify


def test_spec_create_minimal(tmp_path: Path) -> None:
    s = Spec(
        schema_version=1,
        slug="x",
        goal="add /version endpoint",
        constraints=[],
        acceptance_criteria=[],
        ontology={},
        hypothesis=[],
        quality_score=None,
        ambiguity_score=None,
    )
    p = tmp_path / "spec.yaml"
    s.save(p)
    loaded = Spec.load(p)
    assert loaded.slug == "x"
    assert loaded.goal == "add /version endpoint"


def test_spec_validates_verify_kinds(tmp_path: Path) -> None:
    s = Spec(
        schema_version=1, slug="x", goal="g",
        constraints=[],
        acceptance_criteria=[
            AcceptanceCriterion(id="AC01", desc="d", verify=Verify(kind="bogus")),
        ],
        ontology={}, hypothesis=[], quality_score=None, ambiguity_score=None,
    )
    with pytest.raises(SpecError):
        s.validate()


def test_spec_hash_is_deterministic(tmp_path: Path) -> None:
    s = Spec(
        schema_version=1, slug="x", goal="g", constraints=[], acceptance_criteria=[],
        ontology={}, hypothesis=[], quality_score=None, ambiguity_score=None,
    )
    p = tmp_path / "spec.yaml"
    s.save(p)
    h1 = Spec.compute_hash(p)
    h2 = Spec.compute_hash(p)
    assert h1 == h2 and len(h1) == 64
