"""sha256 헬퍼 — Path 또는 str 둘 다 수용 (결함 #7)."""
from pathlib import Path
from mimiron.hash_util import sha256_file, sha256_text


def test_sha256_file_accepts_path_object(tmp_path: Path) -> None:
    p = tmp_path / "hello.txt"
    p.write_text("hello")
    expected = sha256_text("hello")
    assert sha256_file(p) == expected


def test_sha256_file_accepts_str_argument(tmp_path: Path) -> None:
    """worker agent .md의 예시 sha256_file('path/to/file')이 그대로 작동."""
    p = tmp_path / "hello.txt"
    p.write_text("hello")
    expected = sha256_text("hello")
    assert sha256_file(str(p)) == expected


def test_sha256_text_simple() -> None:
    assert sha256_text("") == (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )


def test_sha256_file_chunked_consistency(tmp_path: Path) -> None:
    """chunk_size 변경해도 같은 해시 — large file handling."""
    p = tmp_path / "big.bin"
    p.write_bytes(b"a" * 200_000)
    assert sha256_file(p, chunk_size=1024) == sha256_file(p, chunk_size=65536)
