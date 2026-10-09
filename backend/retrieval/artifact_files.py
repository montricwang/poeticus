"""File integrity helpers shared by Retrieval artifact builders and readers."""
from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_file(path: Path, block_size: int = 8 * 1024 * 1024) -> str:
    """Hash a file without loading its full contents into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(block_size):
            digest.update(block)
    return digest.hexdigest()
