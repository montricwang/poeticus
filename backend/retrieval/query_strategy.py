"""Deterministic multi-query planning for Text Retrieval.

A selected passage is expanded into passage-, sentence-, and clause-level
queries without asking an LLM to rewrite the text. Identical query text is
searched only once while all source spans are retained as provenance.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from backend.retrieval.text_units import split_clause_spans, split_sentence_spans

QueryLevel = Literal["passage", "sentence", "clause"]


@dataclass(frozen=True)
class QueryOrigin:
    level: QueryLevel
    start: int
    end: int


@dataclass(frozen=True)
class QueryVariant:
    text: str
    origins: tuple[QueryOrigin, ...]


def _trim_outer_whitespace(text: str) -> tuple[int, int]:
    start = 0
    end = len(text)
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def build_query_plan(text: str) -> list[QueryVariant]:
    """Return unique passage / sentence / clause queries in stable order.

    The plan preserves the original span for every level that produced a
    query. If passage, sentence and clause text are identical, only one search
    query is emitted with three origins.
    """
    if not isinstance(text, str):
        raise TypeError("text 必须是字符串")

    passage_start, passage_end = _trim_outer_whitespace(text)
    if passage_start == passage_end:
        raise ValueError("text 不能只包含空白字符")

    ordered_texts: list[str] = []
    origins_by_text: dict[str, list[QueryOrigin]] = {}

    def add(level: QueryLevel, start: int, end: int, value: str) -> None:
        if value not in origins_by_text:
            ordered_texts.append(value)
            origins_by_text[value] = []
        origins_by_text[value].append(QueryOrigin(level=level, start=start, end=end))

    passage = text[passage_start:passage_end]
    add("passage", passage_start, passage_end, passage)

    for start, end, sentence in split_sentence_spans(text):
        add("sentence", start, end, sentence)

    for start, end, clause in split_clause_spans(text):
        add("clause", start, end, clause)

    return [
        QueryVariant(text=value, origins=tuple(origins_by_text[value]))
        for value in ordered_texts
    ]
