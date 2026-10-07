import json

import pytest

from scripts.retrieval.faiss_search import (
    build_eligible_work_rows,
    load_index_manifest,
    probe_ranks,
)


def embedding_manifest():
    return {
        "model": "Qwen/Qwen3-Embedding-0.6B",
        "model_fingerprint": "abc123",
        "input_sha256": "deadbeef",
        "chunk_policy": "sentence",
        "embedding_dimension": 1024,
        "dtype": "float16",
        "normalized": True,
        "completed_chunks": 100,
    }


def index_manifest():
    return {
        "manifest_version": 1,
        "engine": "faiss_IndexIVFPQ",
        "source_embedding": embedding_manifest(),
        "nlist": 512,
        "pq_m": 256,
        "pq_bits": 8,
        "nprobe": 64,
        "training_vectors": 50,
        "row_id_contract": (
            "faiss_id == embedding_global_row == chunk_jsonl_logical_row"
        ),
        "status": "complete",
        "index_file": "index.faiss",
        "index_bytes": 4,
        "index_gib": 4 / (1024 ** 3),
        "corpus_vectors": 100,
    }


def test_load_index_manifest_accepts_matching_artifact(tmp_path):
    (tmp_path / "index.faiss").write_bytes(b"FAKE")
    (tmp_path / "manifest.json").write_text(
        json.dumps(index_manifest()),
        encoding="utf-8",
    )

    loaded = load_index_manifest(
        tmp_path,
        embedding_manifest=embedding_manifest(),
    )

    assert loaded["pq_m"] == 256
    assert loaded["corpus_vectors"] == 100


def test_load_index_manifest_rejects_embedding_mismatch(tmp_path):
    (tmp_path / "index.faiss").write_bytes(b"FAKE")
    manifest = index_manifest()
    manifest["source_embedding"]["input_sha256"] = "other"
    (tmp_path / "manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="不匹配"):
        load_index_manifest(
            tmp_path,
            embedding_manifest=embedding_manifest(),
        )


def test_probe_ranks_reports_hit_and_miss():
    assert probe_ranks([9, 3, 7], {3, 4}) == [
        {"global_row": 3, "retrieved_rank": 2},
        {"global_row": 4, "retrieved_rank": None},
    ]



def test_build_eligible_work_rows_overfetches_then_filters():
    ranking_pairs = [
        (0.9, 0),   # self hit
        (0.8, 1),   # clearly later
        (0.7, 2),   # same dynasty, keep
        (0.6, 3),   # duplicate chunk from same work, collapse
        (0.5, 4),   # clearly earlier, keep
    ]
    chunks = {
        0: {"chunk_id": "c0", "text": "self", "work_id": "w-self"},
        1: {"chunk_id": "c1", "text": "later", "work_id": "w-later"},
        2: {"chunk_id": "c2", "text": "same-1", "work_id": "w-same"},
        3: {"chunk_id": "c3", "text": "same-2", "work_id": "w-same"},
        4: {"chunk_id": "c4", "text": "earlier", "work_id": "w-earlier"},
    }
    works = {
        "w-self": {
            "work_id": "w-self",
            "title": "self",
            "author": "a",
            "dynasty": "宋",
            "source_record_id": "s0",
        },
        "w-later": {
            "work_id": "w-later",
            "title": "later",
            "author": "b",
            "dynasty": "清",
            "source_record_id": "s1",
        },
        "w-same": {
            "work_id": "w-same",
            "title": "same",
            "author": "c",
            "dynasty": "宋",
            "source_record_id": "s2",
        },
        "w-earlier": {
            "work_id": "w-earlier",
            "title": "earlier",
            "author": "d",
            "dynasty": "唐",
            "source_record_id": "s3",
        },
    }

    eligible, rank_by_row = build_eligible_work_rows(
        ranking_pairs,
        chunks,
        works,
        current_work_id="w-self",
        target_dynasty="宋",
    )

    assert [item["global_row"] for item in eligible] == [2, 4]
    assert eligible[0]["eligible_rank"] == 1
    assert eligible[0]["raw_rank"] == 3
    assert eligible[1]["chronology_status"] == "clearly_earlier"
    assert rank_by_row == {2: 1, 4: 2}
