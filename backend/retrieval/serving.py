"""Long-lived local runtime for full-corpus Hybrid Retrieval.

Unlike Eval scripts, this module keeps the expensive assets resident:

- one Qwen query encoder;
- sentence FAISS IVFPQ;
- clause FAISS IVFPQ;
- sentence BM25 SQLite;
- compact metadata SQLite.

Request-time lookup never scans the corpus JSONL files.
"""
from __future__ import annotations

import sqlite3
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Sequence

from pydantic import TypeAdapter, ValidationError

from backend.retrieval.chronology import DYNASTY_PERIODS
from backend.retrieval.fanout import (
    ChannelDescriptor,
    ChunkPolicy,
    RetrievalHit,
)
from backend.retrieval.metadata_store import MetadataStore
from backend.retrieval.service import TextRetrievalService

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray


_MANIFEST_ADAPTER = TypeAdapter(dict[str, object])


def _load_json(path: Path) -> dict[str, object]:
    """Read one Manifest whose JSON root must be an object."""
    if not path.is_file():
        raise ValueError(f"manifest 不存在：{path}")
    try:
        return _MANIFEST_ADAPTER.validate_json(
            path.read_text(encoding="utf-8")
        )
    except ValidationError as exc:
        raise ValueError(f"manifest 无法解析：{path}") from exc


def _required_positive_int(manifest: dict[str, object], field: str) -> int:
    """Validate an integer artifact parameter before passing it downstream."""
    value = manifest.get(field)
    if type(value) is not int or value <= 0:
        raise ValueError(f"manifest 缺少有效 {field}：{value!r}")
    return value


def _embedding_source_signature(
    manifest: dict[str, object],
) -> dict[str, object]:
    keys = (
        "model",
        "model_fingerprint",
        "input_sha256",
        "chunk_policy",
        "embedding_dimension",
        "dtype",
        "normalized",
        "completed_chunks",
    )
    missing = [key for key in keys if key not in manifest]
    if missing:
        raise ValueError(
            "Embedding manifest 缺少 serving 字段："
            + ", ".join(missing)
        )
    return {key: manifest[key] for key in keys}


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


def _character_ngrams(text: str, *, min_n: int, max_n: int) -> list[str]:
    runs: list[str] = []
    current: list[str] = []
    for char in text:
        if char.isalnum():
            current.append(char)
        elif current:
            runs.append("".join(current))
            current = []
    if current:
        runs.append("".join(current))

    grams: list[str] = []
    for run in runs:
        for n in range(min_n, max_n + 1):
            if len(run) >= n:
                grams.extend(
                    run[index:index + n]
                    for index in range(len(run) - n + 1)
                )
    return list(dict.fromkeys(grams))


def _build_match_query(text: str, *, min_n: int, max_n: int) -> str | None:
    grams = _character_ngrams(text, min_n=min_n, max_n=max_n)
    if not grams:
        return None
    escaped = [gram.replace('"', '""') for gram in grams]
    return " OR ".join(f'"{gram}"' for gram in escaped)


@dataclass(frozen=True)
class ServingPaths:
    sentence_embedding_dir: Path
    sentence_faiss_dir: Path
    clause_embedding_dir: Path
    clause_faiss_dir: Path
    bm25_sentence_dir: Path
    metadata_db: Path
    model_path: Path


@dataclass(frozen=True)
class ServingCandidate:
    rank: int
    work_id: str
    text: str
    title: str | None
    author: str | None
    dynasty: str | None
    source_record_id: str | None
    chronology_status: str
    support_count: int


@dataclass(frozen=True)
class ServingSearchResult:
    status: str
    query: str
    candidates: tuple[ServingCandidate, ...]
    current_work_aliases: tuple[str, ...]
    timings_ms: dict[str, object]


def _dominant_known_dynasty(counts: dict[str, int]) -> str | None:
    """Pick one corpus dynasty only when the evidence is unambiguous enough.

    Unknown labels are ignored. If two known labels tie for the highest count,
    leave chronology unresolved rather than inventing an ordering.
    """
    ranked = sorted(
        (
            (dynasty, count)
            for dynasty, count in counts.items()
            if dynasty in DYNASTY_PERIODS and count > 0
        ),
        key=lambda item: (-item[1], item[0]),
    )
    if not ranked:
        return None
    if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
        return None
    return ranked[0][0]


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

        kwargs: dict[str, bool | str] = {"local_files_only": True}
        if device:
            kwargs["device"] = device

        self._model = SentenceTransformer(str(model_path), **kwargs)
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
        self._index.nprobe = _required_positive_int(index_manifest, "nprobe")
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
                match_query = _build_match_query(
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


class RetrievalServingRuntime:
    def __init__(
        self,
        paths: ServingPaths,
        *,
        device: str | None = None,
        search_k: int = 100,
        rrf_k: int = 60,
        stage_callback: Callable[[str], None] | None = None,
    ):
        if search_k <= 0:
            raise ValueError("search_k 必须为正整数")

        self.paths = paths
        self.search_k = search_k
        self.rrf_k = rrf_k
        self.startup_profile: dict[str, float | str] = {}

        sentence_manifest = _load_json(
            paths.sentence_embedding_dir / "manifest.json"
        )
        clause_manifest = _load_json(
            paths.clause_embedding_dir / "manifest.json"
        )
        if (
            sentence_manifest.get("model_fingerprint")
            != clause_manifest.get("model_fingerprint")
        ):
            raise ValueError(
                "sentence / clause Embedding model fingerprint 不一致"
            )
        if (
            sentence_manifest.get("embedding_dimension")
            != clause_manifest.get("embedding_dimension")
        ):
            raise ValueError(
                "sentence / clause Embedding dimension 不一致"
            )

        started = time.perf_counter()
        self.encoder = QwenQueryEncoder(
            model_path=paths.model_path,
            dimension=_required_positive_int(
                sentence_manifest, "embedding_dimension"
            ),
            device=device,
        )
        self.startup_profile["model_load_ms"] = (
            time.perf_counter() - started
        ) * 1000
        self.startup_profile["device"] = self.encoder.device
        if stage_callback:
            stage_callback("model")

        started = time.perf_counter()
        self.metadata = MetadataStore(paths.metadata_db)
        metadata_stats = self.metadata.stats()
        if int(metadata_stats.get("sentence_chunks", "-1")) != (
            _required_positive_int(sentence_manifest, "completed_chunks")
        ):
            raise ValueError(
                "Metadata sentence row count 与 Embedding Artifact 不一致"
            )
        if int(metadata_stats.get("clause_chunks", "-1")) != (
            _required_positive_int(clause_manifest, "completed_chunks")
        ):
            raise ValueError(
                "Metadata clause row count 与 Embedding Artifact 不一致"
            )
        if (
            metadata_stats.get("sentence_sha256")
            != sentence_manifest.get("input_sha256")
        ):
            raise ValueError(
                "Metadata sentence source 与 Embedding Artifact 不一致"
            )
        if (
            metadata_stats.get("clause_sha256")
            != clause_manifest.get("input_sha256")
        ):
            raise ValueError(
                "Metadata clause source 与 Embedding Artifact 不一致"
            )
        self.startup_profile["metadata_ready_ms"] = (
            time.perf_counter() - started
        ) * 1000
        if stage_callback:
            stage_callback("metadata")

        started = time.perf_counter()
        self.sentence_dense = FaissDenseChannel(
            name="dense_faiss_sentence",
            policy="sentence",
            embedding_dir=paths.sentence_embedding_dir,
            index_dir=paths.sentence_faiss_dir,
            encoder=self.encoder,
            metadata=self.metadata,
        )
        self.startup_profile["sentence_faiss_load_ms"] = (
            time.perf_counter() - started
        ) * 1000
        if stage_callback:
            stage_callback("sentence_faiss")

        started = time.perf_counter()
        self.clause_dense = FaissDenseChannel(
            name="dense_faiss_clause",
            policy="clause",
            embedding_dir=paths.clause_embedding_dir,
            index_dir=paths.clause_faiss_dir,
            encoder=self.encoder,
            metadata=self.metadata,
        )
        self.startup_profile["clause_faiss_load_ms"] = (
            time.perf_counter() - started
        ) * 1000
        if stage_callback:
            stage_callback("clause_faiss")

        started = time.perf_counter()
        self.lexical = SentenceBm25Channel(
            paths.bm25_sentence_dir
        )
        if (
            metadata_stats.get("work_sha256")
            != self.lexical.manifest.get("work_sha256")
        ):
            raise ValueError(
                "Metadata Work source 与 BM25 Artifact 不一致"
            )
        if (
            metadata_stats.get("sentence_sha256")
            != self.lexical.manifest.get("chunk_sha256")
        ):
            raise ValueError(
                "Metadata sentence source 与 BM25 Artifact 不一致"
            )
        self.startup_profile["bm25_ready_ms"] = (
            time.perf_counter() - started
        ) * 1000
        if stage_callback:
            stage_callback("bm25")

        self.startup_profile["startup_total_ms"] = sum(
            value
            for key, value in self.startup_profile.items()
            if key.endswith("_ms") and key != "startup_total_ms"
            and isinstance(value, float)
        )

    def search(
        self,
        text: str,
        *,
        current_text: str,
        current_author: str | None,
        target_dynasty: str | None,
        final_top_k: int = 8,
        current_work_ids: set[str] | None = None,
    ) -> ServingSearchResult:
        query = text.strip()
        if not query:
            raise ValueError("Retrieval query 不能为空")
        if final_top_k <= 0:
            raise ValueError("final_top_k 必须为正整数")

        aliases_started = time.perf_counter()
        aliases = self.metadata.find_current_work_aliases(
            text=current_text,
            author=current_author,
        )
        aliases.update(current_work_ids or ())

        effective_target_dynasty = target_dynasty
        dynasty_source = "request" if target_dynasty else "unknown"

        if not effective_target_dynasty and aliases:
            alias_works = self.metadata.read_works(aliases)
            alias_counts: dict[str, int] = {}
            for work in alias_works.values():
                if work.dynasty:
                    alias_counts[work.dynasty] = (
                        alias_counts.get(work.dynasty, 0) + 1
                    )
            effective_target_dynasty = _dominant_known_dynasty(
                alias_counts
            )
            if effective_target_dynasty:
                dynasty_source = "current_alias"

        if not effective_target_dynasty and current_author:
            effective_target_dynasty = _dominant_known_dynasty(
                self.metadata.author_dynasty_counts(current_author)
            )
            if effective_target_dynasty:
                dynasty_source = "author_corpus"

        alias_ms = (time.perf_counter() - aliases_started) * 1000

        service = TextRetrievalService(
            [
                self.sentence_dense,
                self.clause_dense,
                self.lexical,
            ],
            per_channel_top_k=self.search_k,
            final_top_k=final_top_k,
            rrf_k=self.rrf_k,
        )

        service_started = time.perf_counter()
        result = service.search(
            query,
            current_work_id=None,
            target_dynasty=effective_target_dynasty,
            current_work_ids=aliases,
        )
        service_ms = (time.perf_counter() - service_started) * 1000

        profiles = {
            "dense_sentence": self.sentence_dense.profile(),
            "dense_clause": self.clause_dense.profile(),
            "bm25_sentence": self.lexical.profile(),
        }
        channel_total = sum(
            float(profile.get("total_ms", 0.0))
            for profile in profiles.values()
        )

        candidates: list[ServingCandidate] = []
        for rank, item in enumerate(result.candidates, 1):
            candidate = item.candidate
            best = min(
                candidate.evidences,
                key=lambda evidence: (
                    evidence.hit.rank,
                    evidence.channel.name,
                    evidence.query_text,
                ),
            )
            candidates.append(
                ServingCandidate(
                    rank=rank,
                    work_id=candidate.work_id,
                    text=best.hit.text,
                    title=candidate.title,
                    author=candidate.author,
                    dynasty=candidate.dynasty,
                    source_record_id=candidate.source_record_id,
                    chronology_status=item.chronology_status,
                    support_count=candidate.support_count,
                )
            )

        timings: dict[str, object] = {
            "current_alias_lookup_ms": alias_ms,
            "target_dynasty": effective_target_dynasty,
            "target_dynasty_source": dynasty_source,
            "service_total_ms": service_ms,
            "orchestration_ms": max(0.0, service_ms - channel_total),
            "channels": profiles,
            "total_ms": alias_ms + service_ms,
        }

        return ServingSearchResult(
            status=result.status,
            query=query,
            candidates=tuple(candidates),
            current_work_aliases=tuple(sorted(aliases)),
            timings_ms=timings,
        )
