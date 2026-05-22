"""sha256 헬퍼."""
from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_file(path: Path | str, chunk_size: int = 65536) -> str:
    h = hashlib.sha256()
    p = Path(path) if not isinstance(path, Path) else path
    with p.open("rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
