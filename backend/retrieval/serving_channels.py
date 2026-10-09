"""Long-lived retrieval channel implementations.

The encoder, FAISS dense channels and SQLite BM25 channel own model/index
access and return ranked RetrievalHit records. Query planning, RRF and
candidate eligibility belong to TextRetrievalService, not this module.
"""
from __future__ import annotations

import sqlite3
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import TYPE_CHECKING, Sequence

from backend.retrieval.fanout import ChannelDescriptor, ChunkPolicy, RetrievalHit
from backend.retrieval.lexical_terms import match_query_or_none
from backend.retrieval.metadata_store import MetadataStore
from backend.retrieval.serving_manifest import (
    _embedding_source_signature,
    _load_json,
    _required_positive_int,
)

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray


def _require_numpy():
    try:
        import numpy as np
    except ImportError as exc:
        raise RuntimeError(
            "Retrieval Serving 需要 NumPy；请安装 requirements-retrieval.txt"
        ) from exc
    return np


def _require_faiss():
    try:
        import faiss
    except ImportError as exc:
        raise RuntimeError(
            "Retrieval Serving 需要 faiss-cpu；请安装 requirements-retrieval.txt"
        ) from exc
    return faiss

class QwenQueryEncoder:
    """Thread-safe bounded query-vector cache around one resident model."""

    def __init__(
        self,
        *,
        model_path: Path,
        dimension: int,
        device: str | None,
        cache_size: int = 256,
    ):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "Retrieval Serving 需要 sentence-transformers；"
                "请安装 requirements-retrieval.txt"
            ) from exc

        self._model = SentenceTransformer(
            str(model_path), local_files_only=True, device=device
        )
        self.dimension = dimension
        self.device = str(self._model.device)
        self._cache_size = cache_size
        self._cache: OrderedDict[str, NDArray[np.float32]] = OrderedDict()
        self._lock = threading.Lock()

    def clear_cache(self) -> None:
        with self._lock:
            self._cache.clear()

    def encode_many(self, queries: Sequence[str]):
        np = _require_numpy()
        with self._lock:
            missing = list(
                dict.fromkeys(
                    query
                    for query in queries
                    if query not in self._cache
                )
            )
            if missing:
                vectors = self._model.encode(
                    missing,
                    normalize_embeddings=True,
                    convert_to_numpy=True,
                    show_progress_bar=False,
                    truncate_dim=self.dimension,
                )
                expected = (len(missing), self.dimension)
                if vectors.shape != expected:
                    raise RuntimeError(
                        f"Query Embedding shape={vectors.shape}，预期 {expected}"
                    )
                for query, vector in zip(missing, vectors, strict=True):
                    self._cache[query] = np.asarray(
                        vector,
                        dtype=np.float32,
                    ).copy()
                    self._cache.move_to_end(query)
                    while len(self._cache) > self._cache_size:
                        self._cache.popitem(last=False)

            output = np.stack(
                [self._cache[query] for query in queries],
                axis=0,
            )
            return np.ascontiguousarray(output, dtype=np.float32)


class FaissDenseChannel:
    def __init__(
        self,
        *,
        name: str,
        policy: ChunkPolicy,
        embedding_dir: Path,
        index_dir: Path,
        encoder: QwenQueryEncoder,
        metadata: MetadataStore,
    ):
        if policy not in {"sentence", "clause"}:
            raise ValueError(f"未知 Dense chunk policy：{policy!r}")

        self.descriptor = ChannelDescriptor(
            name=name,
            method="dense",
            chunk_policy=policy,
        )
        self._policy: ChunkPolicy = policy
        self._encoder = encoder
        self._metadata = metadata
        self._local = threading.local()
        self._index_lock = threading.Lock()

        embedding_manifest = _load_json(
            embedding_dir / "manifest.json"
        )
        index_manifest = _load_json(
            index_dir / "manifest.json"
        )
        if embedding_manifest.get("status") != "complete":
            raise ValueError(f"{policy} Embedding Artifact 尚未完成")
        if embedding_manifest.get("chunk_policy") != policy:
            raise ValueError(
                f"{policy} Embedding manifest chunk_policy 不一致"
            )
        if index_manifest.get("status") != "complete":
            raise ValueError(f"{policy} FAISS index 尚未完成")
        if index_manifest.get("engine") != "faiss_IndexIVFPQ":
            raise ValueError(
                f"{policy} FAISS engine 不支持："
                f"{index_manifest.get('engine')!r}"
            )
        if (
            index_manifest.get("corpus_vectors")
            != embedding_manifest.get("completed_chunks")
        ):
            raise ValueError(
                f"{policy} FAISS / Embedding corpus size 不一致"
            )
        if (
            index_manifest.get("source_embedding")
            != _embedding_source_signature(embedding_manifest)
        ):
            raise ValueError(
                f"{policy} FAISS index 与 Embedding Artifact 不匹配"
            )

        index_file = index_manifest.get("index_file")
        if not isinstance(index_file, str) or not index_file:
            raise ValueError(f"{policy} FAISS manifest 缺少 index_file")

        faiss = _require_faiss()
        self._index = faiss.read_index(str(index_dir / index_file))
        expected = _required_positive_int(embedding_manifest, "completed_chunks")
        if self._index.ntotal != expected:
            raise ValueError(
                f"{policy} FAISS ntotal={self._index.ntotal}，预期 {expected}"
            )
        faiss.ParameterSpace().set_index_parameter(
            self._index, "nprobe", _required_positive_int(index_manifest, "nprobe")
        )
        self.index_manifest = index_manifest
        self.embedding_manifest = embedding_manifest

    def profile(self) -> dict[str, int | float]:
        return dict(getattr(self._local, "profile", {}))

    def search_many(
        self,
        queries: Sequence[str],
        *,
        top_k: int,
    ) -> Sequence[Sequence[RetrievalHit]]:
        if top_k <= 0:
            raise ValueError("top_k 必须为正整数")
        if not queries:
            return []

        started = time.perf_counter()
        encode_started = time.perf_counter()
        vectors = self._encoder.encode_many(queries)
        encode_ms = (time.perf_counter() - encode_started) * 1000

        actual_k = min(top_k, int(self._index.ntotal))
        ann_started = time.perf_counter()
        with self._index_lock:
            scores, ids = self._index.search(vectors, actual_k)
        ann_ms = (time.perf_counter() - ann_started) * 1000

        row_ids = {
            int(row_id)
            for row in ids
            for row_id in row
            if int(row_id) >= 0
        }
        metadata_started = time.perf_counter()
        chunks = self._metadata.read_chunks(
            self._policy,
            row_ids,
        )
        works = self._metadata.read_works(
            chunk.work_id
            for chunk in chunks.values()
        )
        metadata_ms = (time.perf_counter() - metadata_started) * 1000

        output: list[list[RetrievalHit]] = []
        for query_index in range(len(queries)):
            hits: list[RetrievalHit] = []
            for rank, (score, row_id) in enumerate(
                zip(scores[query_index], ids[query_index], strict=True),
                1,
            ):
                row_id = int(row_id)
                if row_id < 0:
                    continue
                chunk = chunks[row_id]
                work = works[chunk.work_id]
                hits.append(
                    RetrievalHit(
                        rank=rank,
                        chunk_id=chunk.chunk_id,
                        work_id=work.work_id,
                        text=chunk.text,
                        title=work.title,
                        author=work.author,
                        dynasty=work.dynasty,
                        source_record_id=work.source_record_id,
                        score=float(score),
                        score_name="ann_inner_product",
                    )
                )
            output.append(hits)

        self._local.profile = {
            "queries": len(queries),
            "top_k": actual_k,
            "encode_ms": encode_ms,
            "ann_ms": ann_ms,
            "metadata_ms": metadata_ms,
            "total_ms": (time.perf_counter() - started) * 1000,
        }
        return output


class SentenceBm25Channel:
    def __init__(self, index_dir: Path):
        self.descriptor = ChannelDescriptor(
            name="lexical_bm25_sentence",
            method="lexical",
            chunk_policy="sentence",
        )
        self._local = threading.local()
        manifest = _load_json(index_dir / "manifest.json")
        if manifest.get("status") != "complete":
            raise ValueError("BM25 Artifact 尚未完成")
        if manifest.get("engine") != "sqlite_fts5":
            raise ValueError(
                f"未知 BM25 engine：{manifest.get('engine')!r}"
            )
        if manifest.get("chunk_policy") != "sentence":
            raise ValueError("Serving 当前只使用 sentence BM25")

        database = manifest.get("database")
        if not isinstance(database, str) or not database:
            raise ValueError("BM25 manifest 缺少 database")
        self._database = (index_dir / database).resolve()
        if not self._database.is_file():
            raise ValueError(
                f"BM25 database 不存在：{self._database}"
            )
        self._min_n = _required_positive_int(manifest, "min_n")
        self._max_n = _required_positive_int(manifest, "max_n")
        self.manifest = manifest

    def profile(self) -> dict[str, int | float]:
        return dict(getattr(self._local, "profile", {}))

    def search_many(
        self,
        queries: Sequence[str],
        *,
        top_k: int,
    ) -> Sequence[Sequence[RetrievalHit]]:
        if top_k <= 0:
            raise ValueError("top_k 必须为正整数")
        if not queries:
            return []

        started = time.perf_counter()
        connection = sqlite3.connect(
            self._database.as_uri() + "?mode=ro",
            uri=True,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        output: list[list[RetrievalHit]] = []
        try:
            for query in queries:
                match_query = match_query_or_none(
                    query,
                    min_n=self._min_n,
                    max_n=self._max_n,
                )
                if match_query is None:
                    output.append([])
                    continue

                rows = connection.execute(
                    """
                    SELECT
                        c.chunk_id,
                        c.work_id,
                        c.text,
                        w.title,
                        w.author,
                        w.dynasty,
                        w.source_record_id,
                        bm25(chunk_fts) AS raw_score
                    FROM chunk_fts
                    JOIN chunks AS c ON c.rowid = chunk_fts.rowid
                    JOIN works AS w ON w.work_id = c.work_id
                    WHERE chunk_fts MATCH ?
                    ORDER BY raw_score ASC, c.rowid ASC
                    LIMIT ?
                    """,
                    (match_query, top_k),
                ).fetchall()
                output.append(
                    [
                        RetrievalHit(
                            rank=rank,
                            chunk_id=row["chunk_id"],
                            work_id=row["work_id"],
                            text=row["text"],
                            title=row["title"],
                            author=row["author"],
                            dynasty=row["dynasty"],
                            source_record_id=row["source_record_id"],
                            score=-float(row["raw_score"]),
                            score_name="bm25",
                        )
                        for rank, row in enumerate(rows, 1)
                    ]
                )
        finally:
            connection.close()

        self._local.profile = {
            "queries": len(queries),
            "top_k": top_k,
            "total_ms": (time.perf_counter() - started) * 1000,
        }
        return output
