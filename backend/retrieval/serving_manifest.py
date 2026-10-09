"""Validation shared by serving startup and retrieval channels.

A manifest describes a rebuildable local artifact. It is not user input;
the checks prevent silently mixing incompatible embeddings and indexes.
"""
from __future__ import annotations

from pathlib import Path

from pydantic import TypeAdapter, ValidationError


_MANIFEST_ADAPTER = TypeAdapter(dict[str, object])


def _load_json(path: Path) -> dict[str, object]:
    """Read one Manifest whose JSON root must be an object."""
    if not path.is_file():
        raise ValueError(f"manifest 不存在：{path}")
    try:
        return _MANIFEST_ADAPTER.validate_json(
            path.read_text(encoding="utf-8")
        )
    except ValidationError as exc:
        raise ValueError(f"manifest 无法解析：{path}") from exc


def _required_positive_int(manifest: dict[str, object], field: str) -> int:
    """Validate an integer artifact parameter before passing it downstream."""
    value = manifest.get(field)
    if type(value) is not int or value <= 0:
        raise ValueError(f"manifest 缺少有效 {field}：{value!r}")
    return value


def _embedding_source_signature(
    manifest: dict[str, object],
) -> dict[str, object]:
    keys = (
        "model",
        "model_fingerprint",
        "input_sha256",
        "chunk_policy",
        "embedding_dimension",
        "dtype",
        "normalized",
        "completed_chunks",
    )
    missing = [key for key in keys if key not in manifest]
    if missing:
        raise ValueError(
            "Embedding manifest 缺少 serving 字段："
            + ", ".join(missing)
        )
    return {key: manifest[key] for key in keys}
