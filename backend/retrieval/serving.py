"""全量 Hybrid Retrieval 的常驻运行与流程编排。

Runtime 启动时加载并验证 Serving 资产，收到查询后通过
TextRetrievalService 组合常驻的检索通道。FAISS、Qwen 编码和
BM25 的实现位于 serving_channels.py。
请求处理期间不扫描原始 Corpus JSONL。"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from backend.retrieval.chronology import DYNASTY_PERIODS
from backend.retrieval.metadata_store import MetadataStore
from backend.retrieval.service import RetrievalStatus, TextRetrievalService
from backend.retrieval.serving_channels import (
    FaissDenseChannel,
    QwenQueryEncoder,
    SentenceBm25Channel,
)
from backend.retrieval.serving_manifest import _load_json, _required_positive_int


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
    status: RetrievalStatus
    query: str
    candidates: tuple[ServingCandidate, ...]
    current_work_aliases: tuple[str, ...]
    timings_ms: dict[str, object]


def _dominant_known_dynasty(counts: dict[str, int]) -> str | None:
    """只有语料证据足够明确时才选定作品的朝代标签。

    忽略未知朝代；如果两个已知朝代标签的计数并列第一，
    则保留年代未知，不能凭空判定先后。
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


def _resolve_target_dynasty(
    metadata: MetadataStore,
    *,
    aliases: set[str],
    target_dynasty: str | None,
    current_author: str | None,
) -> tuple[str | None, str]:
    """按请求、当前作品别名、作者语料的顺序确定朝代。

    若各来源都无法给出明确结果，则保留未知状态；不根据并列
    或无法识别的朝代标签猜测先后。
    """
    if target_dynasty:
        return target_dynasty, "request"

    if aliases:
        alias_works = metadata.read_works(aliases)
        alias_counts: dict[str, int] = {}
        for work in alias_works.values():
            if work.dynasty:
                alias_counts[work.dynasty] = (
                    alias_counts.get(work.dynasty, 0) + 1
                )
        inferred = _dominant_known_dynasty(alias_counts)
        if inferred:
            return inferred, "current_alias"

    if current_author:
        inferred = _dominant_known_dynasty(
            metadata.author_dynasty_counts(current_author)
        )
        if inferred:
            return inferred, "author_corpus"

    return target_dynasty, "unknown"


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

        effective_target_dynasty, dynasty_source = _resolve_target_dynasty(
            self.metadata,
            aliases=aliases,
            target_dynasty=target_dynasty,
            current_author=current_author,
        )

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
