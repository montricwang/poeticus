from pathlib import Path

import pytest

from evals.retrieval import (
    ExpectedMatch,
    RetrievalBenchmarkCase,
    RetrievalBenchmarkDataset,
    RetrievalCaseRun,
    RetrievalHit,
    RetrievalRun,
    benchmark_corpus_coverage,
    evaluate_retrieval,
    first_relevant_rank,
    validate_benchmark_corpus_coverage,
)
from retrieval.schema import ChunkPosition, CorpusChunk


def _dataset():
    return RetrievalBenchmarkDataset(
        schema_version="1",
        dataset_id="retrieval_test",
        dataset_version=1,
        status="draft",
        cases=[
            RetrievalBenchmarkCase(
                id="near_quote",
                query="片片轻鸥落晚沙",
                expected=[
                    ExpectedMatch(
                        text="片片轻鸥下急湍",
                        author="杜甫",
                    )
                ],
                tags=["near_quote"],
                rationale="测试正确来源落在非 Top-1 时的 rank。",
            ),
            RetrievalBenchmarkCase(
                id="miss",
                query="测试未命中",
                expected=[ExpectedMatch(text="正确答案")],
                rationale="测试 miss 进入聚合指标。",
            ),
        ],
    )


def _run():
    return RetrievalRun(
        schema_version="1",
        dataset_id="retrieval_test",
        dataset_version=1,
        retriever="synthetic",
        cases=[
            RetrievalCaseRun(
                case_id="near_quote",
                hits=[
                    RetrievalHit(rank=1, text="无关结果"),
                    RetrievalHit(
                        rank=2,
                        text="另一条无关结果",
                    ),
                    RetrievalHit(
                        rank=3,
                        text="娟娟戏蝶过闲幔，片片轻鸥下急湍。",
                        author="杜甫",
                    ),
                ],
            ),
            RetrievalCaseRun(case_id="miss", hits=[]),
        ],
    )


def test_first_relevant_rank_can_match_target_inside_larger_chunk():
    case = _dataset().cases[0]
    hits = _run().cases[0].hits

    assert first_relevant_rank(case, hits) == 3


def test_retrieval_metrics_use_dataset_case_count_as_denominator():
    metrics = evaluate_retrieval(_dataset(), _run())

    assert metrics.case_ranks == {
        "near_quote": 3,
        "miss": None,
    }
    assert metrics.recall_at == {
        "1": 0.0,
        "5": 0.5,
        "20": 0.5,
    }
    assert metrics.mrr == pytest.approx(1 / 6)


def test_retrieval_case_run_rejects_non_contiguous_or_out_of_order_ranks():
    with pytest.raises(ValueError, match="1..N"):
        RetrievalCaseRun(
            case_id="near_quote",
            hits=[
                RetrievalHit(rank=1, text="第一条"),
                RetrievalHit(rank=3, text="第三条"),
            ],
        )

    with pytest.raises(ValueError, match="1..N"):
        RetrievalCaseRun(
            case_id="near_quote",
            hits=[
                RetrievalHit(rank=2, text="第二条"),
                RetrievalHit(rank=1, text="第一条"),
            ],
        )


def test_evaluate_retrieval_rejects_wrong_dataset_identity():
    wrong_id_run = RetrievalRun(
        schema_version="1",
        dataset_id="another_dataset",
        dataset_version=1,
        retriever="synthetic",
        cases=_run().cases,
    )
    with pytest.raises(ValueError, match="dataset_id"):
        evaluate_retrieval(_dataset(), wrong_id_run)

    wrong_version_run = RetrievalRun(
        schema_version="1",
        dataset_id="retrieval_test",
        dataset_version=2,
        retriever="synthetic",
        cases=_run().cases,
    )
    with pytest.raises(ValueError, match="dataset_version"):
        evaluate_retrieval(_dataset(), wrong_version_run)


def test_evaluate_retrieval_rejects_missing_or_unknown_cases():
    missing_case_run = RetrievalRun(
        schema_version="1",
        dataset_id="retrieval_test",
        dataset_version=1,
        retriever="synthetic",
        cases=[_run().cases[0]],
    )
    with pytest.raises(ValueError, match="缺少 Case"):
        evaluate_retrieval(_dataset(), missing_case_run)

    unknown_case_run = RetrievalRun(
        schema_version="1",
        dataset_id="retrieval_test",
        dataset_version=1,
        retriever="synthetic",
        cases=[
            *_run().cases,
            RetrievalCaseRun(case_id="unknown_case", hits=[]),
        ],
    )
    with pytest.raises(ValueError, match="未知 Case"):
        evaluate_retrieval(_dataset(), unknown_case_run)



def _chunk(
    *,
    chunk_id: str,
    text: str,
    author: str | None = None,
    title: str | None = None,
    source_record_id: str = "source-record",
) -> CorpusChunk:
    return CorpusChunk(
        chunk_id=chunk_id,
        work_id=f"work-{chunk_id}",
        policy="clause",
        chunk_index=0,
        text=text,
        positions=[ChunkPosition(paragraph_index=0, unit_index=0)],
        source="synthetic",
        source_record_id=source_record_id,
        author=author,
        title=title,
    )


def test_benchmark_corpus_coverage_separates_missing_target_from_retriever_miss():
    dataset = _dataset()
    chunks = [
        _chunk(
            chunk_id="dufu",
            text="娟娟戏蝶过闲幔，片片轻鸥下急湍。",
            author="杜甫",
        )
    ]

    coverage = benchmark_corpus_coverage(dataset, chunks)

    assert coverage["near_quote"] == ["dufu"]
    assert coverage["miss"] == []

    with pytest.raises(ValueError, match="Corpus coverage"):
        validate_benchmark_corpus_coverage(dataset, chunks)


def test_public_retrieval_dataset_v01_is_small_and_schema_valid():
    path = Path(__file__).resolve().parents[1] / "evals" / "retrieval_cases.json"
    dataset = RetrievalBenchmarkDataset.model_validate_json(
        path.read_text(encoding="utf-8")
    )

    assert dataset.dataset_id == "poeticus_retrieval_v01"
    assert dataset.dataset_version == 1
    assert len(dataset.cases) == 6

    tags = {tag for case in dataset.cases for tag in case.tags}
    assert {
        "near_quote",
        "adapted_quote",
        "compressed_cue",
        "transformed_use",
    } <= tags


def test_public_retrieval_dataset_can_be_coverage_checked_independently():
    path = Path(__file__).resolve().parents[1] / "evals" / "retrieval_cases.json"
    dataset = RetrievalBenchmarkDataset.model_validate_json(
        path.read_text(encoding="utf-8")
    )

    chunks = []
    for index, case in enumerate(dataset.cases):
        expected = case.expected[0]
        chunks.append(
            _chunk(
                chunk_id=f"expected-{index}",
                text=expected.text,
                author=expected.author,
                title=expected.title,
                source_record_id=expected.source_record_id or f"record-{index}",
            )
        )

    coverage = validate_benchmark_corpus_coverage(dataset, chunks)

    assert all(coverage[case.id] for case in dataset.cases)
