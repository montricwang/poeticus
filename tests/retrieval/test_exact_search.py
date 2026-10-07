import json

import pytest

from scripts.retrieval.exact_search import (
    build_dynasty_row_mask,
    build_result_rows,
    candidate_prior_dynasties,
    load_manifest,
    merge_top_k,
    read_selected_chunks,
    read_selected_works,
    resolve_model_path,
)


def _write_manifest(tmp_path, *, status="complete"):
    artifact_dir = tmp_path / "embeddings"
    artifact_dir.mkdir()
    (artifact_dir / "shard_00000.npy").write_bytes(b"placeholder")
    (artifact_dir / "shard_00001.npy").write_bytes(b"placeholder")
    manifest = {
        "status": status,
        "model": "Qwen/Qwen3-Embedding-0.6B",
        "model_fingerprint": "model-hash",
        "input_sha256": "corpus-hash",
        "embedding_dimension": 1024,
        "completed_chunks": 3,
        "completed_shards": [
            {"start": 0, "end": 2, "file": "shard_00000.npy"},
            {"start": 2, "end": 3, "file": "shard_00001.npy"},
        ],
    }
    (artifact_dir / "manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
    return artifact_dir


def test_load_manifest_accepts_complete_contiguous_artifact(tmp_path):
    artifact_dir = _write_manifest(tmp_path)

    manifest = load_manifest(artifact_dir)

    assert manifest["completed_chunks"] == 3
    assert manifest["embedding_dimension"] == 1024


def test_load_manifest_rejects_incomplete_artifact(tmp_path):
    artifact_dir = _write_manifest(tmp_path, status="running")

    with pytest.raises(ValueError, match="尚未完成"):
        load_manifest(artifact_dir)


def test_merge_top_k_keeps_global_best_and_stable_row_order():
    actual = merge_top_k(
        [(0.8, 9), (0.7, 3)],
        [(0.9, 8), (0.8, 2)],
        top_k=3,
    )

    assert actual == [(0.9, 8), (0.8, 2), (0.8, 9)]


def test_read_selected_chunks_uses_logical_nonblank_row_index(tmp_path):
    path = tmp_path / "chunks.jsonl"
    rows = [
        {"chunk_id": "c0", "work_id": "w0", "text": "甲"},
        {"chunk_id": "c1", "work_id": "w1", "text": "乙"},
        {"chunk_id": "c2", "work_id": "w2", "text": "丙"},
    ]
    path.write_text(
        json.dumps(rows[0], ensure_ascii=False)
        + "\n\n"
        + json.dumps(rows[1], ensure_ascii=False)
        + "\n"
        + json.dumps(rows[2], ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )

    actual = read_selected_chunks(path, [0, 2])

    assert actual[0]["chunk_id"] == "c0"
    assert actual[2]["chunk_id"] == "c2"


def test_read_selected_works_reads_only_requested_ids(tmp_path):
    path = tmp_path / "works.jsonl"
    rows = [
        {"work_id": "w0", "title": "甲"},
        {"work_id": "w1", "title": "乙"},
        {"work_id": "w2", "title": "丙"},
    ]
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )

    actual = read_selected_works(path, ["w2", "w0"])

    assert set(actual) == {"w0", "w2"}
    assert actual["w2"]["title"] == "丙"


def test_build_result_rows_joins_chunk_and_work_metadata():
    ranking = [(0.91, 7)]
    chunks = {
        7: {
            "chunk_id": "c7",
            "work_id": "w7",
            "text": "客舍青青柳色新。",
            "start": 8,
            "end": 17,
        }
    }
    works = {
        "w7": {
            "work_id": "w7",
            "title": "送元二使安西",
            "author": "王维",
            "dynasty": "唐",
            "source_record_id": "唐.csv:7",
        }
    }

    rows = build_result_rows(ranking, chunks, works)

    assert rows[0]["rank"] == 1
    assert rows[0]["cosine"] == 0.91
    assert rows[0]["chunk"]["text"] == "客舍青青柳色新。"
    assert rows[0]["work"]["author"] == "王维"


def test_resolve_model_path_uses_artifact_fingerprint_by_default(monkeypatch, tmp_path):
    from scripts.retrieval import exact_search

    monkeypatch.setattr(exact_search, "DEFAULT_MODEL_ROOT", tmp_path)
    manifest = {"model_fingerprint": "abcdef1234567890"}

    path = resolve_model_path(manifest, None)

    assert path == (tmp_path / "Qwen3-Embedding-0.6B-abcdef123456").resolve()


def test_resolve_model_path_keeps_explicit_override(tmp_path):
    requested = tmp_path / "custom-model"

    path = resolve_model_path(
        {"model_fingerprint": "abcdef1234567890"},
        requested,
    )

    assert path == requested.resolve()


def test_candidate_prior_dynasties_keeps_transition_period_for_song():
    allowed = candidate_prior_dynasties("宋")

    assert "唐" in allowed
    assert "隋" in allowed
    assert "唐末宋初" in allowed
    assert "辽" not in allowed
    assert "宋" not in allowed


def test_build_dynasty_row_mask_aligns_with_chunk_rows(tmp_path):
    work_path = tmp_path / "works.jsonl"
    chunk_path = tmp_path / "chunks.jsonl"

    works = [
        {"work_id": "tang", "dynasty": "唐"},
        {"work_id": "song", "dynasty": "宋"},
    ]
    chunks = [
        {"chunk_id": "c0", "work_id": "song", "text": "甲"},
        {"chunk_id": "c1", "work_id": "tang", "text": "乙"},
        {"chunk_id": "c2", "work_id": "tang", "text": "丙"},
    ]
    work_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in works),
        encoding="utf-8",
    )
    chunk_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in chunks),
        encoding="utf-8",
    )

    mask = build_dynasty_row_mask(
        work_path=work_path,
        chunk_path=chunk_path,
        allowed_dynasties={"唐"},
        expected_chunks=3,
    )

    assert mask.tolist() == [False, True, True]
