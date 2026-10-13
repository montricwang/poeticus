"""供 Retrieval 资产构建和读取共同使用的文件完整性工具。"""
from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_file(path: Path, block_size: int = 8 * 1024 * 1024) -> str:
    """分块计算文件 SHA256，避免一次性读入完整文件。"""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(block_size):
            digest.update(block)
    return digest.hexdigest()
