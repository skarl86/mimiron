"""artifacts.json + sha256 검증."""
from pathlib import Path
import pytest
from mimiron.artifacts import Artifacts, DeclaredFile, ArtifactError
from mimiron.hash_util import sha256_file


def test_sha256_file(tmp_path: Path) -> None:
    p = tmp_path / "a.txt"
    p.write_text("hello")
    h1 = sha256_file(p)
    p.write_text("hello")
    assert sha256_file(p) == h1
    p.write_text("hello!")
    assert sha256_file(p) != h1


def test_artifacts_verify_passes_when_files_match(tmp_path: Path) -> None:
    f = tmp_path / "x.py"
    f.write_text("print('hi')\n")
    a = Artifacts(
        schema_version=1,
        task_id="T01",
        declared_files=[
            DeclaredFile(
                path="x.py",
                action="create",
                pre_hash=None,
                post_hash=sha256_file(f),
                pre_mtime=None,
                post_mtime="2026-05-22T00:00:00Z",
            )
        ],
        worker_summary="created x.py",
    )
    # verify against actual file state
    a.verify(root=tmp_path)


def test_artifacts_verify_fails_when_hash_drifts(tmp_path: Path) -> None:
    f = tmp_path / "x.py"
    f.write_text("v1\n")
    a = Artifacts(
        schema_version=1,
        task_id="T01",
        declared_files=[
            DeclaredFile(
                path="x.py",
                action="create",
                pre_hash=None,
                post_hash="ZZZZ",
                pre_mtime=None,
                post_mtime="2026-05-22T00:00:00Z",
            )
        ],
        worker_summary="lying",
    )
    with pytest.raises(ArtifactError, match="hash mismatch"):
        a.verify(root=tmp_path)


def test_artifacts_verify_fails_when_declared_file_missing(tmp_path: Path) -> None:
    a = Artifacts(
        schema_version=1,
        task_id="T01",
        declared_files=[
            DeclaredFile(
                path="missing.py",
                action="create",
                pre_hash=None,
                post_hash="abc",
                pre_mtime=None,
                post_mtime="2026-05-22T00:00:00Z",
            )
        ],
        worker_summary="x",
    )
    with pytest.raises(ArtifactError, match="missing"):
        a.verify(root=tmp_path)


def test_artifacts_save_and_load_roundtrip(tmp_path: Path) -> None:
    a = Artifacts(
        schema_version=1,
        task_id="T01",
        declared_files=[],
        worker_summary="empty",
    )
    p = tmp_path / "artifacts.json"
    a.save(p)
    loaded = Artifacts.load(p)
    assert loaded.task_id == "T01"
