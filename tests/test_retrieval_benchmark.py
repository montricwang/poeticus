import json
from pathlib import Path

import pytest

from evals.retrieval import (
    PoetryCorpusRecord,
    RetrievalCase,
    RetrievalDataset,
    RetrievalRanking,
    RetrievalRunInput,
    evaluate_retrieval_run,
    load_corpus_jsonl,
    load_retrieval_dataset,
    score_case,
    validate_dataset_against_corpus,
)


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_CORPUS = ROOT / "evals" / "retrieval_corpus_sample.jsonl"
SAMPLE_DATASET = ROOT / "evals" / "retrieval_cases.json"


def test_public_retrieval_fixture_matches_contract():
    corpus = load_corpus_jsonl(SAMPLE_CORPUS)
    dataset = load_retrieval_dataset(SAMPLE_DATASET)

    assert dataset.dataset_id == "poeticus_retrieval_seed"
    assert len(dataset.cases) == 2
    assert len(corpus) >= 4

    validate_dataset_against_corpus(dataset, corpus)


def test_score_case_reports_first_rank_recall_and_rr():
    case = RetrievalCase(
        id="multi_relevant_case",
        query="query",
        relevant_record_ids=["a", "b"],
        rationale="exercise multi-target metrics",
    )

    metrics = score_case(
        case,
        ["c", "a", "d", "b"],
        ks=(1, 2, 4),
    )

    assert metrics.first_relevant_rank == 2
    assert metrics.reciprocal_rank == pytest.approx(0.5)
    assert metrics.recall_at_k == {
        "1": 0.0,
        "2": 0.5,
        "4": 1.0,
    }


def test_score_case_keeps_miss_visible():
    case = RetrievalCase(
        id="miss_case",
        query="query",
        relevant_record_ids=["a"],
        rationale="exercise miss handling",
    )

    metrics = score_case(case, ["b", "c"], ks=(1, 5))

    assert metrics.first_relevant_rank is None
    assert metrics.reciprocal_rank == 0.0
    assert metrics.recall_at_k == {"1": 0.0, "5": 0.0}


def test_evaluate_retrieval_run_aggregates_cases():
    corpus = [
        PoetryCorpusRecord(
            id="a",
            work_id="work-a",
            text="A",
            source="fixture",
        ),
        PoetryCorpusRecord(
            id="b",
            work_id="work-b",
            text="B",
            source="fixture",
        ),
        PoetryCorpusRecord(
            id="c",
            work_id="work-c",
            text="C",
            source="fixture",
        ),
    ]
    dataset = RetrievalDataset(
        schema_version="1",
        dataset_id="fixture_dataset",
        dataset_version=1,
        status="draft",
        cases=[
            RetrievalCase(
                id="case_one",
                query="q1",
                relevant_record_ids=["a"],
                rationale="fixture",
            ),
            RetrievalCase(
                id="case_two",
                query="q2",
                relevant_record_ids=["b"],
                rationale="fixture",
            ),
        ],
    )
    run = RetrievalRunInput(
        schema_version="1",
        dataset_id="fixture_dataset",
        retriever_id="fixture_retriever",
        rankings=[
            RetrievalRanking(case_id="case_one", ranked_record_ids=["a", "c"]),
            RetrievalRanking(case_id="case_two", ranked_record_ids=["c", "b"]),
        ],
    )

    metrics = evaluate_retrieval_run(dataset, corpus, run, ks=(1, 2))

    assert metrics.case_count == 2
    assert metrics.mrr == pytest.approx(0.75)
    assert metrics.mean_recall_at_k == {"1": 0.5, "2": 1.0}


def test_evaluate_retrieval_run_rejects_unknown_record_ids():
    corpus = [
        PoetryCorpusRecord(
            id="a",
            work_id="work-a",
            text="A",
            source="fixture",
        )
    ]
    dataset = RetrievalDataset(
        schema_version="1",
        dataset_id="fixture_dataset",
        dataset_version=1,
        status="draft",
        cases=[
            RetrievalCase(
                id="case_one",
                query="q1",
                relevant_record_ids=["a"],
                rationale="fixture",
            )
        ],
    )
    run = RetrievalRunInput(
        schema_version="1",
        dataset_id="fixture_dataset",
        retriever_id="fixture_retriever",
        rankings=[
            RetrievalRanking(case_id="case_one", ranked_record_ids=["missing"])
        ],
    )

    with pytest.raises(ValueError, match="Corpus 外"):
        evaluate_retrieval_run(dataset, corpus, run)


def test_sample_rankings_are_explicitly_synthetic():
    payload = json.loads(
        (ROOT / "evals" / "retrieval_rankings_sample.json").read_text(
            encoding="utf-8"
        )
    )

    assert payload["retriever_id"] == "fixture_manual_order"
