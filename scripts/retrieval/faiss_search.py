"""Search a full FAISS IVFPQ serving index with a real text query.

This is the first full-corpus ANN diagnostic after the serving index build:

    query text
    -> the same Qwen query encoder used by the Embedding Artifact
    -> full FAISS IVFPQ index
    -> ANN Top-K global rows
    -> recover Chunk / Work metadata

FAISS scores are approximate inner-product scores from the compressed index.
They are not exact cosine scores and not literary-relation scores.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from scripts.retrieval.artifact_search import (
    encode_query_for_artifact,
    load_artifact_manifest,
    resolve_chunk_path,
    resolve_query_model_path,
)
from scripts.retrieval.exact_search import (
    DEFAULT_WORKS,
    find_probe_rows,
    read_selected_chunks,
    read_selected_works,
    sha256_file,
)
from scripts.retrieval.faiss_full_index import (
    INDEX_FILENAME,
    MANIFEST_FILENAME,
    source_signature,
)

DEFAULT_TOP_K = 20


def _require_numpy():
    try:
        import numpy as np
    except ImportError as exc:
        raise RuntimeError(
            "FAISS search 需要 NumPy；请安装 requirements-retrieval.txt"
        ) from exc
    return np


def _require_faiss():
    try:
        import faiss
    except ImportError as exc:
        raise RuntimeError(
            "FAISS search 需要 faiss-cpu；请安装 requirements-retrieval.txt"
        ) from exc
    return faiss


def load_index_manifest(
    index_dir: Path,
    *,
    embedding_manifest: dict,
) -> dict:
    manifest_path = index_dir / MANIFEST_FILENAME
    if not manifest_path.is_file():
        raise ValueError(f"FAISS manifest 不存在：{manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "complete":
        raise ValueError(
            f"FAISS index 尚未完成：status={manifest.get('status')!r}"
        )
    if manifest.get("engine") != "faiss_IndexIVFPQ":
        raise ValueError(
            f"尚不支持该 FAISS engine：{manifest.get('engine')!r}"
        )

    expected_source = source_signature(embedding_manifest)
    actual_source = manifest.get("source_embedding")
    if actual_source != expected_source:
        raise ValueError(
            "FAISS index 与 Embedding Artifact 不匹配；"
            "不能保证 row id / 向量语义一致"
        )

    expected_count = embedding_manifest["completed_chunks"]
    if manifest.get("corpus_vectors") != expected_count:
        raise ValueError(
            "FAISS manifest corpus_vectors 与 Embedding Artifact 不一致"
        )

    index_file = manifest.get("index_file")
    if not isinstance(index_file, str) or not index_file:
        raise ValueError("FAISS manifest 缺少 index_file")
    index_path = index_dir / index_file
    if not index_path.is_file():
        raise ValueError(f"FAISS index 文件不存在：{index_path}")
    if index_path.name != INDEX_FILENAME:
        # The current builder uses a stable filename. Refuse silent drift until
        # there is a real need to support multiple index-file layouts.
        raise ValueError(
            f"FAISS index_file={index_path.name!r}，预期 {INDEX_FILENAME!r}"
        )

    expected_bytes = manifest.get("index_bytes")
    if isinstance(expected_bytes, int) and index_path.stat().st_size != expected_bytes:
        raise ValueError("FAISS index 文件大小与 manifest 不一致")

    return manifest


def probe_ranks(
    ranking_rows: list[int],
    probe_rows: set[int],
) -> list[dict]:
    rank_by_row = {
        int(row_id): rank
        for rank, row_id in enumerate(ranking_rows, 1)
    }
    return [
        {
            "global_row": row_id,
            "retrieved_rank": rank_by_row.get(row_id),
        }
        for row_id in sorted(probe_rows)
    ]


def run_faiss_search(
    *,
    query: str,
    artifact_dir: Path,
    index_dir: Path,
    work_path: Path = DEFAULT_WORKS,
    chunk_path: Path | None = None,
    model_path: Path | None = None,
    top_k: int = DEFAULT_TOP_K,
    probe_text: str | None = None,
    probe_author: str | None = None,
    device: str | None = None,
    verify_input_hash: bool = False,
) -> dict:
    if not query.strip():
        raise ValueError("query 不能为空")
    if top_k <= 0:
        raise ValueError("top_k 必须为正整数")
    if probe_author and not probe_text:
        raise ValueError("probe_author 必须和 probe_text 一起使用")

    np = _require_numpy()
    faiss = _require_faiss()

    artifact_dir = artifact_dir.expanduser().resolve()
    index_dir = index_dir.expanduser().resolve()
    work_path = work_path.expanduser().resolve()

    embedding_manifest = load_artifact_manifest(artifact_dir)
    index_manifest = load_index_manifest(
        index_dir,
        embedding_manifest=embedding_manifest,
    )
    chunk_path = resolve_chunk_path(embedding_manifest, chunk_path)
    model_path = resolve_query_model_path(embedding_manifest, model_path)

    if verify_input_hash:
        if not chunk_path.is_file():
            raise ValueError(f"Chunk JSONL 不存在：{chunk_path}")
        actual_hash = sha256_file(chunk_path)
        if actual_hash != embedding_manifest.get("input_sha256"):
            raise ValueError(
                "Chunk JSONL SHA256 与 Embedding manifest 不一致；"
                "不能安全回查 FAISS row id"
            )

    probe_rows_set: set[int] = set()
    if probe_text:
        probe_rows_set = find_probe_rows(
            work_path=work_path,
            chunk_path=chunk_path,
            probe_text=probe_text,
            probe_author=probe_author,
        )
        if not probe_rows_set:
            raise ValueError(
                "没有找到符合 probe 条件的 Chunk："
                f"text={probe_text!r}, author={probe_author!r}"
            )

    query_vector, selected_device = encode_query_for_artifact(
        query=query.strip(),
        model_path=model_path,
        manifest=embedding_manifest,
        device=device,
    )
    queries = np.ascontiguousarray(
        query_vector.reshape(1, -1),
        dtype=np.float32,
    )

    index_path = index_dir / index_manifest["index_file"]
    load_started = time.perf_counter()
    index = faiss.read_index(str(index_path))
    load_seconds = time.perf_counter() - load_started

    expected_count = embedding_manifest["completed_chunks"]
    if index.ntotal != expected_count:
        raise ValueError(
            f"FAISS ntotal={index.ntotal}，预期 {expected_count}"
        )

    nprobe = index_manifest["nprobe"]
    index.nprobe = nprobe

    # Warm once so the measured query latency does not include first-call setup.
    index.search(queries, min(top_k, int(index.ntotal)))
    search_started = time.perf_counter()
    scores, ids = index.search(
        queries,
        min(top_k, int(index.ntotal)),
    )
    search_seconds = time.perf_counter() - search_started

    ranking_pairs = [
        (float(score), int(row_id))
        for score, row_id in zip(scores[0], ids[0], strict=True)
        if int(row_id) >= 0
    ]
    ranking_rows = [row_id for _, row_id in ranking_pairs]

    selected_rows = set(ranking_rows) | probe_rows_set
    chunks = read_selected_chunks(chunk_path, selected_rows)
    works = read_selected_works(
        work_path,
        [chunks[row_id]["work_id"] for row_id in selected_rows],
    )

    ranking = []
    for rank, (score, row_id) in enumerate(ranking_pairs, 1):
        chunk = chunks[row_id]
        work = works[chunk["work_id"]]
        ranking.append(
            {
                "rank": rank,
                "ann_score": round(score, 6),
                "global_row": row_id,
                "chunk": {
                    "chunk_id": chunk["chunk_id"],
                    "text": chunk["text"],
                    "start": chunk.get("start"),
                    "end": chunk.get("end"),
                },
                "work": {
                    "work_id": work["work_id"],
                    "title": work.get("title"),
                    "author": work.get("author"),
                    "dynasty": work.get("dynasty"),
                    "source_record_id": work.get("source_record_id"),
                },
            }
        )

    probes = []
    for item in probe_ranks(ranking_rows, probe_rows_set):
        row_id = item["global_row"]
        chunk = chunks[row_id]
        work = works[chunk["work_id"]]
        probes.append(
            {
                **item,
                "chunk": {
                    "chunk_id": chunk["chunk_id"],
                    "text": chunk["text"],
                },
                "work": {
                    "work_id": work["work_id"],
                    "title": work.get("title"),
                    "author": work.get("author"),
                    "dynasty": work.get("dynasty"),
                    "source_record_id": work.get("source_record_id"),
                },
            }
        )

    return {
        "query": query.strip(),
        "model": embedding_manifest["model"],
        "chunk_policy": embedding_manifest["chunk_policy"],
        "device": selected_device,
        "dimension": embedding_manifest["embedding_dimension"],
        "corpus_chunks": expected_count,
        "top_k": top_k,
        "index": {
            "engine": index_manifest["engine"],
            "nlist": index_manifest["nlist"],
            "pq_m": index_manifest["pq_m"],
            "pq_bits": index_manifest["pq_bits"],
            "nprobe": nprobe,
            "index_gib": index_manifest["index_gib"],
            "load_seconds": load_seconds,
            "search_ms": search_seconds * 1000,
        },
        "ranking": ranking,
        "probes": probes,
        "note": (
            "ann_score 是压缩 IVFPQ 的近似 inner-product score；"
            "只用于候选排序，不是 Exact cosine，也不是文学关系分数。"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="使用完整 FAISS IVFPQ index 做真实文本 ANN 检索"
    )
    parser.add_argument("query", help="要检索的当前诗句或片段")
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--index-dir", type=Path, required=True)
    parser.add_argument("--chunks", type=Path)
    parser.add_argument("--works", type=Path, default=DEFAULT_WORKS)
    parser.add_argument("--model-path", type=Path)
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--probe-text")
    parser.add_argument("--probe-author")
    parser.add_argument("--device")
    parser.add_argument("--verify-input-hash", action="store_true")
    args = parser.parse_args()

    try:
        result = run_faiss_search(
            query=args.query,
            artifact_dir=args.artifact_dir,
            index_dir=args.index_dir,
            work_path=args.works,
            chunk_path=args.chunks,
            model_path=args.model_path,
            top_k=args.top_k,
            probe_text=args.probe_text,
            probe_author=args.probe_author,
            device=args.device,
            verify_input_hash=args.verify_input_hash,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
