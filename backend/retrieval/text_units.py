"""Shared text-unit splitting rules for Retrieval.

The same sentence / clause boundaries are used when building the corpus and
when planning deterministic queries. Keeping them in one place prevents the
query side from silently drifting away from the indexed corpus policy.
"""
from __future__ import annotations

from typing import Iterator

SENTENCE_END = frozenset("。！？!?")
CLAUSE_END = frozenset("，,；;。！？!?")
CLOSING_MARKS = frozenset("”’」』】）》")


def _trim_span(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def _has_semantic_text(text: str, end_marks: frozenset[str]) -> bool:
    return any(
        not ch.isspace() and ch not in end_marks and ch not in CLOSING_MARKS
        for ch in text
    )


def _split_spans(
    text: str,
    end_marks: frozenset[str],
) -> Iterator[tuple[int, int, str]]:
    start = 0
    index = 0
    size = len(text)

    while index < size:
        if text[index] not in end_marks:
            index += 1
            continue

        index += 1
        while index < size and text[index] in end_marks:
            index += 1
        while index < size and text[index] in CLOSING_MARKS:
            index += 1

        left, right = _trim_span(text, start, index)
        candidate = text[left:right]
        if candidate and _has_semantic_text(candidate, end_marks):
            yield left, right, candidate
        start = index

    left, right = _trim_span(text, start, size)
    candidate = text[left:right]
    if candidate and _has_semantic_text(candidate, end_marks):
        yield left, right, candidate


def split_sentence_spans(text: str) -> Iterator[tuple[int, int, str]]:
    """Yield sentence-level spans after 。！？!?."""
    yield from _split_spans(text, SENTENCE_END)


def split_clause_spans(text: str) -> Iterator[tuple[int, int, str]]:
    """Yield clause-level spans after commas, semicolons, or sentence ends."""
    yield from _split_spans(text, CLAUSE_END)
