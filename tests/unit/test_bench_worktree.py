"""git worktree isolation."""
import subprocess
from pathlib import Path
import pytest
from mimiron.bench.worktree_iso import IsolationError, isolate_at_ref  # noqa: F401


@pytest.fixture
def tiny_repo(tmp_path: Path) -> Path:
    """git init + 2 commits."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    (repo / "a.txt").write_text("v1\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "c1"], cwd=repo, check=True, capture_output=True)
    (repo / "a.txt").write_text("v2\n")
    subprocess.run(["git", "commit", "-am", "c2"], cwd=repo, check=True, capture_output=True)
    return repo


def test_isolate_at_head(tiny_repo: Path, tmp_path: Path) -> None:
    iso_dir = tmp_path / "iso"
    with isolate_at_ref(repo=tiny_repo, ref="HEAD~1", dest=iso_dir) as iso:
        assert iso.exists()
        assert (iso / "a.txt").read_text() == "v1\n"
    # 컨텍스트 종료 후 worktree 자동 제거
    rc = subprocess.run(
        ["git", "worktree", "list"],
        cwd=tiny_repo,
        capture_output=True,
        text=True,
        check=True,
    )
    assert str(iso_dir) not in rc.stdout


def test_isolate_does_not_touch_original_workdir(tiny_repo: Path, tmp_path: Path) -> None:
    (tiny_repo / "untracked.txt").write_text("dirty")
    iso_dir = tmp_path / "iso"
    with isolate_at_ref(repo=tiny_repo, ref="HEAD~1", dest=iso_dir):
        pass
    # 원본 작업트리 untracked 파일 보존
    assert (tiny_repo / "untracked.txt").read_text() == "dirty"
    # 원본의 a.txt는 v2 (변경 없음)
    assert (tiny_repo / "a.txt").read_text() == "v2\n"
