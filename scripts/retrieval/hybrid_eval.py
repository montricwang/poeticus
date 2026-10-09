"""Evaluate the current Hybrid Retrieval pipeline on local full indexes.

This is a product-level diagnostic, not a new retrieval implementation:

    text
    -> deterministic passage / sentence / clause Query Plan
    -> Dense sentence FAISS
    -> Dense clause FAISS
    -> Lexical sentence BM25
    -> Work-level RRF
    -> Candidate Eligibility
    -> final candidate ranking

It deliberately reuses backend query/fusion/eligibility logic. The local
artifact adapters exist only to feed real indexes into that pipeline before a
production RetrievalChannel implementation is committed.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import NotRequired, TypedDict

from backend.retrieval.eligibility import apply_candidate_eligibility
from backend.retrieval.fanout import (
    ChannelDescriptor,
    QueryChannelResult,
    RetrievalHit,
)
from backend.retrieval.fusion import DEFAULT_RRF_K, fuse_candidates_rrf
from backend.retrieval.query_strategy import build_query_plan
from scripts.retrieval.artifact_search import (
    QWEN_MODEL,
    load_artifact_manifest,
    resolve_chunk_path,
    resolve_query_model_path,
)
from scripts.retrieval.exact_search import (
    DEFAULT_WORKS,
    ensure_model_snapshot,
    read_selected_chunks,
    read_selected_works,
)
from scripts.retrieval.faiss_search import load_index_manifest
from scripts.retrieval.lexical_bm25 import (
    DEFAULT_INDEX_ROOT,
    search_bm25,
)

DEFAULT_SENTENCE_BM25 = DEFAULT_INDEX_ROOT / "bm25_sentence_2_3"
DEFAULT_SEARCH_K = 100
DEFAULT_FINAL_TOP_K = 20


def _require_numpy():
    try:
        import numpy as np
    except ImportError as exc:
        raise RuntimeError(
            "Hybrid Eval 需要 NumPy；请安装 requirements-retrieval.txt"
        ) from exc
    return np


def _require_faiss():
    try:
        import faiss
    except ImportError as exc:
        raise RuntimeError(
            "Hybrid Eval 需要 faiss-cpu；请安装 requirements-retrieval.txt"
        ) from exc
    return faiss


class ChannelStats(TypedDict, total=False):
    channel: str
    index_gib: float
    nprobe: int
    search_k: int
    load_seconds: float
    batch_search_ms: float
    query_count: int


class ProbeSupport(TypedDict):
    query: str
    query_origins: list[str]
    channel: str
    rank: int | None
    text: str | None
    score: float | None
    score_name: str | None


class CandidateEvidence(TypedDict):
    query: str
    channel: str
    rank: int
    text: str


class CandidateRow(TypedDict):
    work_id: str
    title: str | None
    author: str | None
    dynasty: str | None
    rrf_score: float
    best_rank: int
    support_count: int
    best_evidence: CandidateEvidence
    supports: list[CandidateEvidence]
    chronology_status: NotRequired[str]


class RankedCandidate(CandidateRow):
    rank: int


class ProbeRow(TypedDict):
    work_id: str
    fused_rank: int | None
    eligible_rank: int | None
    list_supports: list[ProbeSupport]
    missing_lists: list[dict[str, object]]


class HybridEvaluation(TypedDict):
    text: str
    query_plan: list[dict[str, object]]
    search_k_per_channel: int
    rrf_k: int
    channels: list[ChannelStats]
    candidate_pool: dict[str, int]
    ranking: list[RankedCandidate]
    probes: list[ProbeRow]
    note: str


def find_probe_work_ids(
    *,
    work_path: Path,
    probe_text: str,
    probe_author: str | None,
) -> set[str]:
    if not probe_text:
        raise ValueError("probe_text 不能为空")

    work_ids: set[str] = set()
    with work_path.open(encoding="utf-8") as stream:
        for line_no, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                work = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Work JSONL 第 {line_no} 行无法解析"
                ) from exc
            if probe_author and work.get("author") != probe_author:
                continue
            if probe_text in work.get("content", ""):
                work_ids.add(work["work_id"])
    return work_ids


def _dense_results(
    *,
    plan,
    artifact_dir: Path,
    index_dir: Path,
    work_path: Path,
    query_vectors,
    search_k: int,
) -> tuple[list[QueryChannelResult], ChannelStats]:
    np = _require_numpy()
    faiss = _require_faiss()

    artifact_dir = artifact_dir.expanduser().resolve()
    index_dir = index_dir.expanduser().resolve()
    embedding_manifest = load_artifact_manifest(artifact_dir)
    if embedding_manifest["model"] != QWEN_MODEL:
        raise ValueError(
            "当前 Hybrid Eval 只使用 Qwen sentence / clause Dense Artifact"
        )

    index_manifest = load_index_manifest(
        index_dir,
        embedding_manifest=embedding_manifest,
    )
    chunk_path = resolve_chunk_path(embedding_manifest, None)

    index_path = index_dir / index_manifest["index_file"]
    load_started = time.perf_counter()
    index = faiss.read_index(str(index_path))
    load_seconds = time.perf_counter() - load_started
    index.nprobe = index_manifest["nprobe"]

    if index.ntotal != embedding_manifest["completed_chunks"]:
        raise ValueError(
            f"FAISS ntotal={index.ntotal} 与 Artifact "
            f"{embedding_manifest['completed_chunks']} 不一致"
        )

    actual_k = min(search_k, int(index.ntotal))
    queries = np.ascontiguousarray(query_vectors, dtype=np.float32)
    index.search(queries[:1], actual_k)
    started = time.perf_counter()
    scores, ids = index.search(queries, actual_k)
    search_seconds = time.perf_counter() - started

    selected_rows = {
        int(row_id)
        for row in ids
        for row_id in row
        if int(row_id) >= 0
    }
    chunks = read_selected_chunks(chunk_path, selected_rows)
    works = read_selected_works(
        work_path,
        [chunks[row_id]["work_id"] for row_id in selected_rows],
    )

    policy = embedding_manifest["chunk_policy"]
    descriptor = ChannelDescriptor(
        name=f"dense_faiss_{policy}",
        method="dense",
        chunk_policy=policy,
    )
    results: list[QueryChannelResult] = []

    for query_index, variant in enumerate(plan):
        hits = []
        for rank, (score, row_id) in enumerate(
            zip(scores[query_index], ids[query_index], strict=True),
            1,
        ):
            row_id = int(row_id)
            if row_id < 0:
                continue
            chunk = chunks[row_id]
            work = works[chunk["work_id"]]
            hits.append(
                RetrievalHit(
                    rank=rank,
                    chunk_id=chunk["chunk_id"],
                    work_id=work["work_id"],
                    text=chunk["text"],
                    title=work.get("title"),
                    author=work.get("author"),
                    dynasty=work.get("dynasty"),
                    source_record_id=work.get("source_record_id"),
                    score=float(score),
                    score_name="ann_inner_product",
                )
            )
        results.append(
            QueryChannelResult(
                query=variant,
                channel=descriptor,
                hits=tuple(hits),
            )
        )

    return results, {
        "channel": descriptor.name,
        "index_gib": index_manifest["index_gib"],
        "nprobe": index_manifest["nprobe"],
        "search_k": actual_k,
        "load_seconds": load_seconds,
        "batch_search_ms": search_seconds * 1000,
        "query_count": len(plan),
    }


def _lexical_results(
    *,
    plan,
    index_dir: Path,
    search_k: int,
) -> tuple[list[QueryChannelResult], ChannelStats]:
    descriptor = ChannelDescriptor(
        name="lexical_bm25_sentence",
        method="lexical",
        chunk_policy="sentence",
    )
    results: list[QueryChannelResult] = []
    started = time.perf_counter()

    for variant in plan:
        response = search_bm25(
            query=variant.text,
            index_dir=index_dir,
            top_k=search_k,
        )
        if response["chunk_policy"] != "sentence":
            raise ValueError("当前 Hybrid Eval 只接 sentence BM25")
        hits = tuple(
            RetrievalHit(
                rank=item["rank"],
                chunk_id=item["chunk"]["chunk_id"],
                work_id=item["work"]["work_id"],
                text=item["chunk"]["text"],
                title=item["work"]["title"],
                author=item["work"]["author"],
                dynasty=item["work"]["dynasty"],
                source_record_id=item["work"]["source_record_id"],
                score=item["bm25_score"],
                score_name="bm25",
            )
            for item in response["ranking"]
        )
        results.append(
            QueryChannelResult(
                query=variant,
                channel=descriptor,
                hits=hits,
            )
        )

    elapsed = time.perf_counter() - started
    return results, {
        "channel": descriptor.name,
        "search_k": search_k,
        "batch_search_ms": elapsed * 1000,
        "query_count": len(plan),
    }


def probe_list_supports(
    channel_results,
    probe_work_ids: set[str],
) -> list[ProbeSupport]:
    """Report where a known target appears before RRF.

    Each QueryVariant × RetrievalChannel is one ranked list. This diagnostic
    makes RRF behavior auditable by showing whether a target is broadly
    supported or survives only in one particular query granularity/channel.
    """
    supports: list[ProbeSupport] = []
    for result in channel_results:
        match = next(
            (
                hit
                for hit in result.hits
                if hit.work_id in probe_work_ids
            ),
            None,
        )
        supports.append(
            {
                "query": result.query.text,
                "query_origins": [
                    origin.level
                    for origin in result.query.origins
                ],
                "channel": result.channel.name,
                "rank": None if match is None else match.rank,
                "text": None if match is None else match.text,
                "score": None if match is None else match.score,
                "score_name": None if match is None else match.score_name,
            }
        )
    return supports


def _candidate_row(candidate, chronology_status: str | None = None) -> CandidateRow:
    best = min(
        candidate.evidences,
        key=lambda evidence: (
            evidence.hit.rank,
            evidence.channel.name,
            evidence.query_text,
        ),
    )
    row: CandidateRow = {
        "work_id": candidate.work_id,
        "title": candidate.title,
        "author": candidate.author,
        "dynasty": candidate.dynasty,
        "rrf_score": candidate.rrf_score,
        "best_rank": candidate.best_rank,
        "support_count": candidate.support_count,
        "best_evidence": {
            "query": best.query_text,
            "channel": best.channel.name,
            "rank": best.hit.rank,
            "text": best.hit.text,
        },
        "supports": [
            {
                "query": evidence.query_text,
                "channel": evidence.channel.name,
                "rank": evidence.hit.rank,
                "text": evidence.hit.text,
            }
            for evidence in candidate.evidences
        ],
    }
    if chronology_status is not None:
        row["chronology_status"] = chronology_status
    return row


def evaluate_hybrid(
    *,
    text: str,
    sentence_artifact_dir: Path,
    sentence_index_dir: Path,
    clause_artifact_dir: Path,
    clause_index_dir: Path,
    bm25_sentence_dir: Path = DEFAULT_SENTENCE_BM25,
    work_path: Path = DEFAULT_WORKS,
    current_work_id: str | None,
    current_work_ids: set[str] | None = None,
    target_dynasty: str | None,
    probe_text: str | None,
    probe_author: str | None,
    search_k: int = DEFAULT_SEARCH_K,
    final_top_k: int = DEFAULT_FINAL_TOP_K,
    rrf_k: int = DEFAULT_RRF_K,
    device: str | None = None,
) -> HybridEvaluation:
    if search_k <= 0 or final_top_k <= 0:
        raise ValueError("search_k / final_top_k 必须为正整数")
    if probe_author and not probe_text:
        raise ValueError("probe_author 必须和 probe_text 一起使用")

    np = _require_numpy()
    plan = tuple(build_query_plan(text))
    queries = [variant.text for variant in plan]

    sentence_manifest = load_artifact_manifest(
        sentence_artifact_dir.expanduser().resolve()
    )
    clause_manifest = load_artifact_manifest(
        clause_artifact_dir.expanduser().resolve()
    )
    for manifest in (sentence_manifest, clause_manifest):
        if manifest["model"] != QWEN_MODEL:
            raise ValueError("Hybrid Eval 的 Dense Artifact 必须使用同一 Qwen 模型")
    if (
        sentence_manifest["model_fingerprint"]
        != clause_manifest["model_fingerprint"]
    ):
        raise ValueError("sentence / clause Dense Artifact 模型 fingerprint 不一致")
    if (
        sentence_manifest["embedding_dimension"]
        != clause_manifest["embedding_dimension"]
    ):
        raise ValueError("sentence / clause Dense Artifact dimension 不一致")

    model_path = resolve_query_model_path(sentence_manifest, None)
    ensure_model_snapshot(
        model_path,
        sentence_manifest["model_fingerprint"],
    )
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError(
            "Hybrid Eval 需要 sentence-transformers；"
            "请安装 requirements-retrieval.txt"
        ) from exc

    kwargs: dict[str, bool | str] = {"local_files_only": True}
    if device:
        kwargs["device"] = device
    model = SentenceTransformer(str(model_path), **kwargs)
    dimension = sentence_manifest["embedding_dimension"]
    query_vectors = model.encode(
        queries,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
        truncate_dim=dimension,
    )
    query_vectors = np.ascontiguousarray(query_vectors, dtype=np.float32)

    sentence_results, sentence_stats = _dense_results(
        plan=plan,
        artifact_dir=sentence_artifact_dir,
        index_dir=sentence_index_dir,
        work_path=work_path,
        query_vectors=query_vectors,
        search_k=search_k,
    )
    clause_results, clause_stats = _dense_results(
        plan=plan,
        artifact_dir=clause_artifact_dir,
        index_dir=clause_index_dir,
        work_path=work_path,
        query_vectors=query_vectors,
        search_k=search_k,
    )
    lexical_results, lexical_stats = _lexical_results(
        plan=plan,
        index_dir=bm25_sentence_dir,
        search_k=search_k,
    )

    channel_results = [
        *sentence_results,
        *clause_results,
        *lexical_results,
    ]
    fused = fuse_candidates_rrf(
        channel_results,
        top_k=None,
        rrf_k=rrf_k,
    )
    eligibility = apply_candidate_eligibility(
        fused,
        current_work_id=current_work_id,
        current_work_ids=current_work_ids,
        target_dynasty=target_dynasty,
    )

    probe_work_ids: set[str] = set()
    if probe_text:
        probe_work_ids = find_probe_work_ids(
            work_path=work_path,
            probe_text=probe_text,
            probe_author=probe_author,
        )
        if not probe_work_ids:
            raise ValueError(
                "没有找到符合 probe 条件的 Work："
                f"text={probe_text!r}, author={probe_author!r}"
            )

    fused_rank_by_work = {
        candidate.work_id: rank
        for rank, candidate in enumerate(fused, 1)
    }
    eligible_rank_by_work = {
        item.candidate.work_id: rank
        for rank, item in enumerate(eligibility.eligible, 1)
    }
    list_supports = probe_list_supports(
        channel_results,
        probe_work_ids,
    )
    probes: list[ProbeRow] = [
        {
            "work_id": work_id,
            "fused_rank": fused_rank_by_work.get(work_id),
            "eligible_rank": eligible_rank_by_work.get(work_id),
            "list_supports": [
                item
                for item in list_supports
                if item["rank"] is not None
            ],
            "missing_lists": [
                {
                    "query": item["query"],
                    "query_origins": item["query_origins"],
                    "channel": item["channel"],
                }
                for item in list_supports
                if item["rank"] is None
            ],
        }
        for work_id in sorted(probe_work_ids)
    ]

    query_plan: list[dict[str, object]] = [
            {
                "text": variant.text,
                "origins": [
                    {
                        "level": origin.level,
                        "start": origin.start,
                        "end": origin.end,
                    }
                    for origin in variant.origins
                ],
            }
            for variant in plan
    ]

    return {
        "text": text,
        "query_plan": query_plan,
        "search_k_per_channel": search_k,
        "rrf_k": rrf_k,
        "channels": [
            sentence_stats,
            clause_stats,
            lexical_stats,
        ],
        "candidate_pool": {
            "fused_works": len(fused),
            "eligible_works": len(eligibility.eligible),
            "rejected_works": len(eligibility.rejected),
        },
        "ranking": [
            {
                "rank": rank,
                **_candidate_row(
                    item.candidate,
                    item.chronology_status,
                ),
            }
            for rank, item in enumerate(
                eligibility.eligible[:final_top_k],
                1,
            )
        ],
        "probes": probes,
        "note": (
            "这是 Hybrid Retrieval 诊断：Dense sentence + Dense clause + "
            "sentence BM25 先各自召回，再按 Work-level RRF 融合并应用 "
            "Candidate Eligibility；RRF 分数不是文学关系概率。"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="用本地 full indexes 验证 Poeticus Hybrid Retrieval"
    )
    parser.add_argument("text")
    parser.add_argument("--sentence-artifact-dir", type=Path, required=True)
    parser.add_argument("--sentence-index-dir", type=Path, required=True)
    parser.add_argument("--clause-artifact-dir", type=Path, required=True)
    parser.add_argument("--clause-index-dir", type=Path, required=True)
    parser.add_argument(
        "--bm25-sentence-dir",
        type=Path,
        default=DEFAULT_SENTENCE_BM25,
    )
    parser.add_argument("--works", type=Path, default=DEFAULT_WORKS)
    parser.add_argument("--current-work-id")
    parser.add_argument("--target-dynasty")
    parser.add_argument("--probe-text")
    parser.add_argument("--probe-author")
    parser.add_argument("--search-k", type=int, default=DEFAULT_SEARCH_K)
    parser.add_argument("--final-top-k", type=int, default=DEFAULT_FINAL_TOP_K)
    parser.add_argument("--rrf-k", type=int, default=DEFAULT_RRF_K)
    parser.add_argument("--device")
    args = parser.parse_args()

    try:
        result = evaluate_hybrid(
            text=args.text,
            sentence_artifact_dir=args.sentence_artifact_dir,
            sentence_index_dir=args.sentence_index_dir,
            clause_artifact_dir=args.clause_artifact_dir,
            clause_index_dir=args.clause_index_dir,
            bm25_sentence_dir=args.bm25_sentence_dir,
            work_path=args.works.expanduser().resolve(),
            current_work_id=args.current_work_id,
            current_work_ids=None,
            target_dynasty=args.target_dynasty,
            probe_text=args.probe_text,
            probe_author=args.probe_author,
            search_k=args.search_k,
            final_top_k=args.final_top_k,
            rrf_k=args.rrf_k,
            device=args.device,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
