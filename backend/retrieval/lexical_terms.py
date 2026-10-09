"""Shared character n-gram and SQLite FTS5 query representation.

Offline BM25 indexing and online Serving must use the same token boundaries.
Callers decide separately whether a query with no tokens is an error or a
legitimate empty retrieval result.
"""
from __future__ import annotations

from collections.abc import Iterable, Iterator


def iter_character_runs(text: str) -> Iterator[str]:
    """Yield alphanumeric Unicode runs; punctuation acts as a boundary."""
    current: list[str] = []
    for char in text:
        if char.isalnum():
            current.append(char)
            continue
        if current:
            yield "".join(current)
            current = []
    if current:
        yield "".join(current)


def character_ngrams(
    text: str,
    *,
    min_n: int = 2,
    max_n: int = 3,
) -> list[str]:
    """Produce corpus and query terms with identical Unicode boundaries."""
    if min_n <= 0 or max_n < min_n:
        raise ValueError("n-gram 范围必须满足 0 < min_n <= max_n")

    grams: list[str] = []
    for run in iter_character_runs(text):
        for n in range(min_n, max_n + 1):
            if len(run) < n:
                continue
            grams.extend(run[index:index + n] for index in range(len(run) - n + 1))
    return grams


def unique_in_order(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(values))


def match_query_or_none(
    query: str,
    *,
    min_n: int = 2,
    max_n: int = 3,
) -> str | None:
    """Build an FTS5 MATCH expression; leave empty-result policy to callers."""
    grams = unique_in_order(character_ngrams(query, min_n=min_n, max_n=max_n))
    if not grams:
        return None
    escaped = [gram.replace('"', '""') for gram in grams]
    return " OR ".join(f'"{gram}"' for gram in escaped)
