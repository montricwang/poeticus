import pytest

from evals.retrieval import (
    ExpectedMatch,
    RetrievalBenchmarkCase,
    RetrievalBenchmarkDataset,
    RetrievalCaseRun,
    RetrievalHit,
    RetrievalRun,
    evaluate_retrieval,
    first_relevant_rank,
)


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
