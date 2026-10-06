"""Poetry Retrieval Benchmark 的最小数据契约与指标。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PoetryCorpusRecord(BaseModel):
    """一个可被 Retriever 返回的最小诗词片段。"""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_.:-]*$")
    work_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    author: str | None = None
    dynasty: str | None = None
    title: str | None = None
    source: str = Field(min_length=1)
    source_record_id: str | None = None
    chunk_type: Literal["clause", "sentence", "clause_pair", "other"] = "other"
    position: int | None = Field(default=None, ge=0)


class RetrievalCase(BaseModel):
    """一个 Retrieval Query 与已知相关记录集合。"""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]+$")
    query: str = Field(min_length=1)
    relevant_record_ids: list[str] = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    rationale: str = Field(min_length=1)

    @model_validator(mode="after")
    def relevant_ids_must_be_unique(self):
        if len(self.relevant_record_ids) != len(set(self.relevant_record_ids)):
            raise ValueError("relevant_record_ids 必须唯一")
        return self


class RetrievalDataset(BaseModel):
    """一组 Retrieval Cases。"""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"]
    dataset_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]+$")
    dataset_version: int = Field(ge=1)
    status: Literal["draft", "active"]
    cases: list[RetrievalCase] = Field(min_length=1)

    @model_validator(mode="after")
    def case_ids_must_be_unique(self):
        ids = [case.id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("Retrieval case id 必须唯一")
        return self


class RetrievalRanking(BaseModel):
    """一个 Retriever 对某个 Case 返回的有序 record ids。"""

    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]+$")
    ranked_record_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def ranked_ids_must_be_unique(self):
        if len(self.ranked_record_ids) != len(set(self.ranked_record_ids)):
            raise ValueError("ranked_record_ids 必须唯一")
        return self


class RetrievalRunInput(BaseModel):
    """与具体 Retriever 解耦的排序结果输入。"""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"]
    dataset_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]+$")
    retriever_id: str = Field(min_length=1)
    rankings: list[RetrievalRanking] = Field(min_length=1)

    @model_validator(mode="after")
    def ranking_case_ids_must_be_unique(self):
        ids = [ranking.case_id for ranking in self.rankings]
        if len(ids) != len(set(ids)):
            raise ValueError("Ranking case id 必须唯一")
        return self


class RetrievalCaseMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    first_relevant_rank: int | None
    reciprocal_rank: float
    recall_at_k: dict[str, float]


class RetrievalRunMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str
    retriever_id: str
    case_count: int
    mrr: float
    mean_recall_at_k: dict[str, float]
    cases: list[RetrievalCaseMetrics]


def load_corpus_jsonl(path: Path) -> list[PoetryCorpusRecord]:
    records: list[PoetryCorpusRecord] = []
    seen_ids: set[str] = set()

    with path.open("r", encoding="utf-8") as handle:
        for line_no, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                record = PoetryCorpusRecord.model_validate_json(line)
            except Exception as exc:  # Pydantic 会提供具体字段错误
                raise ValueError(f"{path}:{line_no} 语料记录无效: {exc}") from exc

            if record.id in seen_ids:
                raise ValueError(f"Corpus record id 重复: {record.id}")
            seen_ids.add(record.id)
            records.append(record)

    if not records:
        raise ValueError("Corpus 不能为空")
    return records


def load_retrieval_dataset(path: Path) -> RetrievalDataset:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return RetrievalDataset.model_validate(payload)


def load_retrieval_run(path: Path) -> RetrievalRunInput:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return RetrievalRunInput.model_validate(payload)


def validate_dataset_against_corpus(
    dataset: RetrievalDataset,
    corpus: list[PoetryCorpusRecord],
) -> None:
    corpus_ids = {record.id for record in corpus}
    missing = sorted(
        {
            record_id
            for case in dataset.cases
            for record_id in case.relevant_record_ids
            if record_id not in corpus_ids
        }
    )
    if missing:
        raise ValueError(
            "Dataset 引用了 Corpus 中不存在的 record id: " + ", ".join(missing)
        )


def _normalize_ks(ks: tuple[int, ...] | list[int]) -> tuple[int, ...]:
    normalized = tuple(sorted(set(ks)))
    if not normalized or normalized[0] <= 0:
        raise ValueError("K 必须是正整数")
    return normalized


def score_case(
    case: RetrievalCase,
    ranked_record_ids: list[str],
    *,
    ks: tuple[int, ...] | list[int] = (1, 5, 20),
) -> RetrievalCaseMetrics:
    ks = _normalize_ks(ks)
    relevant = set(case.relevant_record_ids)

    first_rank = next(
        (
            rank
            for rank, record_id in enumerate(ranked_record_ids, start=1)
            if record_id in relevant
        ),
        None,
    )
    reciprocal_rank = 0.0 if first_rank is None else 1.0 / first_rank

    recall_at_k = {
        str(k): len(relevant.intersection(ranked_record_ids[:k])) / len(relevant)
        for k in ks
    }

    return RetrievalCaseMetrics(
        case_id=case.id,
        first_relevant_rank=first_rank,
        reciprocal_rank=reciprocal_rank,
        recall_at_k=recall_at_k,
    )


def evaluate_retrieval_run(
    dataset: RetrievalDataset,
    corpus: list[PoetryCorpusRecord],
    run: RetrievalRunInput,
    *,
    ks: tuple[int, ...] | list[int] = (1, 5, 20),
) -> RetrievalRunMetrics:
    ks = _normalize_ks(ks)
    validate_dataset_against_corpus(dataset, corpus)

    if run.dataset_id != dataset.dataset_id:
        raise ValueError(
            f"Run dataset_id={run.dataset_id!r} 与 Dataset {dataset.dataset_id!r} 不一致"
        )

    case_by_id = {case.id: case for case in dataset.cases}
    ranking_by_id = {ranking.case_id: ranking for ranking in run.rankings}

    unknown_cases = sorted(set(ranking_by_id) - set(case_by_id))
    if unknown_cases:
        raise ValueError("Run 包含未知 Case: " + ", ".join(unknown_cases))

    missing_cases = sorted(set(case_by_id) - set(ranking_by_id))
    if missing_cases:
        raise ValueError("Run 缺少 Case: " + ", ".join(missing_cases))

    corpus_ids = {record.id for record in corpus}
    unknown_records = sorted(
        {
            record_id
            for ranking in run.rankings
            for record_id in ranking.ranked_record_ids
            if record_id not in corpus_ids
        }
    )
    if unknown_records:
        raise ValueError("Run 返回了 Corpus 外的 record id: " + ", ".join(unknown_records))

    case_metrics = [
        score_case(
            case_by_id[ranking.case_id],
            ranking.ranked_record_ids,
            ks=ks,
        )
        for ranking in run.rankings
    ]

    case_count = len(case_metrics)
    mrr = sum(item.reciprocal_rank for item in case_metrics) / case_count
    mean_recall_at_k = {
        str(k): sum(item.recall_at_k[str(k)] for item in case_metrics) / case_count
        for k in ks
    }

    return RetrievalRunMetrics(
        dataset_id=dataset.dataset_id,
        retriever_id=run.retriever_id,
        case_count=case_count,
        mrr=mrr,
        mean_recall_at_k=mean_recall_at_k,
        cases=case_metrics,
    )
