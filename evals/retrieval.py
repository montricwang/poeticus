"""Retrieval Benchmark 的模型无关数据契约与基础指标。"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


_WHITESPACE = re.compile(r"\s+")


class ExpectedMatch(BaseModel):
    """一个可接受的正确检索目标。

    text 使用“应被召回的核心文字”，因此 sentence / clause_pair chunk
    只要包含该文字也可以判为命中。
    """

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    author: str | None = None
    title: str | None = None
    source_record_id: str | None = None


class RetrievalBenchmarkCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]+$")
    query: str = Field(min_length=1)
    expected: list[ExpectedMatch] = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    rationale: str = Field(min_length=1)


class RetrievalBenchmarkDataset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"]
    dataset_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]+$")
    dataset_version: int = Field(ge=1)
    status: Literal["draft", "active"]
    cases: list[RetrievalBenchmarkCase] = Field(min_length=1)

    @model_validator(mode="after")
    def case_ids_must_be_unique(self):
        ids = [case.id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("Retrieval case id 必须唯一")
        return self


class RetrievalHit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rank: int = Field(ge=1)
    text: str = Field(min_length=1)
    score: float | None = None
    chunk_id: str | None = None
    work_id: str | None = None
    source_record_id: str | None = None
    author: str | None = None
    title: str | None = None


class RetrievalCaseRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    hits: list[RetrievalHit] = Field(default_factory=list)


class RetrievalRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"]
    retriever: str = Field(min_length=1)
    cases: list[RetrievalCaseRun]

    @model_validator(mode="after")
    def case_ids_must_be_unique(self):
        ids = [case.case_id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("Retrieval run case id 必须唯一")
        return self


class RetrievalMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_count: int = Field(ge=1)
    recall_at: dict[str, float]
    mrr: float = Field(ge=0, le=1)
    case_ranks: dict[str, int | None]


def _normalize_text(text: str) -> str:
    return _WHITESPACE.sub("", text)


def _hit_matches_expected(hit: RetrievalHit, expected: ExpectedMatch) -> bool:
    if _normalize_text(expected.text) not in _normalize_text(hit.text):
        return False
    if expected.author is not None and hit.author != expected.author:
        return False
    if expected.title is not None and hit.title != expected.title:
        return False
    if (
        expected.source_record_id is not None
        and hit.source_record_id != expected.source_record_id
    ):
        return False
    return True


def first_relevant_rank(
    case: RetrievalBenchmarkCase,
    hits: list[RetrievalHit],
) -> int | None:
    for hit in sorted(hits, key=lambda item: item.rank):
        if any(
            _hit_matches_expected(hit, expected)
            for expected in case.expected
        ):
            return hit.rank
    return None


def evaluate_retrieval(
    dataset: RetrievalBenchmarkDataset,
    run: RetrievalRun,
    *,
    ks: tuple[int, ...] = (1, 5, 20),
) -> RetrievalMetrics:
    if not ks or any(k < 1 for k in ks):
        raise ValueError("ks 必须全部是正整数")

    run_by_case = {case.case_id: case for case in run.cases}
    case_ranks: dict[str, int | None] = {}

    for case in dataset.cases:
        case_run = run_by_case.get(case.id)
        hits = case_run.hits if case_run else []
        case_ranks[case.id] = first_relevant_rank(case, hits)

    case_count = len(dataset.cases)
    recall_at = {
        str(k): sum(
            1
            for rank in case_ranks.values()
            if rank is not None and rank <= k
        )
        / case_count
        for k in ks
    }
    mrr = sum(
        1 / rank
        for rank in case_ranks.values()
        if rank is not None
    ) / case_count

    return RetrievalMetrics(
        case_count=case_count,
        recall_at=recall_at,
        mrr=mrr,
        case_ranks=case_ranks,
    )
