"""Contracts shared by offline BM25 and online Retrieval Serving."""
from __future__ import annotations

import hashlib

import pytest

from backend.retrieval.artifact_files import sha256_file
from backend.retrieval.lexical_terms import (
    character_ngrams,
    match_query_or_none,
)
from scripts.retrieval.build_metadata_store import (
    DEFAULT_OUTPUT,
    DEFAULT_WORKS,
)
from scripts.retrieval.lexical_bm25 import (
    DEFAULT_INDEX_ROOT,
    build_match_query,
    character_ngrams as builder_character_ngrams,
)


@pytest.mark.parametrize(
    "text",
    [
        "片片轻鸥，落晚沙。",
        "abc-def ABC123",
        "山月。山月。",
        "甲A乙 B3",
        "",
        "！ 。",
    ],
)
def test_offline_and_online_bm25_terms_match(text: str) -> None:
    expected = character_ngrams(text, min_n=2, max_n=3)
    assert builder_character_ngrams(text, min_n=2, max_n=3) == expected


@pytest.mark.parametrize(
    "query",
    ["片片轻鸥，落晚沙。", "山月。山月。", "abc-def ABC123", "B3", "甲A乙"],
)
def test_diagnostic_query_uses_serving_fts5_expression(query: str) -> None:
    assert build_match_query(query) == match_query_or_none(query)


@pytest.mark.parametrize("query", ["", " ", "？！", "A"])
def test_empty_query_keeps_distinct_diagnostic_and_serving_contracts(query: str) -> None:
    assert match_query_or_none(query) is None
    with pytest.raises(ValueError, match="没有可检索词项"):
        build_match_query(query)


@pytest.mark.parametrize("min_n,max_n", [(0, 3), (4, 3)])
def test_shared_term_validation(min_n: int, max_n: int) -> None:
    with pytest.raises(ValueError, match="n-gram"):
        match_query_or_none("abc", min_n=min_n, max_n=max_n)
    with pytest.raises(ValueError, match="n-gram"):
        build_match_query("abc", min_n=min_n, max_n=max_n)


def test_artifact_fingerprint_is_based_on_file_bytes(tmp_path) -> None:
    path = tmp_path / "artifact.bin"
    content = b"\x00abc\xff\n" * 17
    path.write_bytes(content)
    expected = hashlib.sha256(content).hexdigest()
    assert sha256_file(path, block_size=5) == expected


def test_build_paths_use_shared_data_root() -> None:
    from backend.data_paths import RETRIEVAL_CORPUS_ROOT, RETRIEVAL_ROOT

    assert DEFAULT_WORKS == RETRIEVAL_CORPUS_ROOT / "werneror_works.jsonl"
    assert DEFAULT_OUTPUT == RETRIEVAL_ROOT / "serving/retrieval_metadata.sqlite3"
    assert DEFAULT_INDEX_ROOT == RETRIEVAL_ROOT / "lexical"
