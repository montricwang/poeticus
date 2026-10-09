"""Run exact Retrieval against any supported embedding Artifact.

The Artifact manifest is the source of truth for:
- embedding model;
- chunk policy;
- vector dimension;
- corpus size.

Supported experimental Artifacts:
- Qwen3-Embedding-0.6B
- BERT-CCPoem v1.0

This module keeps the search path identical across model/chunk comparisons.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from collections.abc import Mapping
from typing import TypedDict

from pydantic import TypeAdapter

from backend.data_paths import RETRIEVAL_CORPUS_ROOT

from backend.retrieval.artifact_files import sha256_file
from backend.retrieval.embedding_artifact import (
    ArtifactManifest as ArtifactManifest,
    BERT_CCPOEM_MODEL as BERT_CCPOEM_MODEL,
    QWEN_MODEL as QWEN_MODEL,
    SUPPORTED_MODELS as SUPPORTED_MODELS,
    load_artifact_manifest as load_artifact_manifest,
)
from backend.retrieval.chronology import candidate_prior_dynasties

from scripts.retrieval.exact_search import (
    DEFAULT_DATA_ROOT as DEFAULT_DATA_ROOT,
    DEFAULT_MODEL_ROOT,
    DEFAULT_TOP_K,
    build_dynasty_row_mask,
    build_result_rows,
    ensure_model_snapshot,
    exact_search,
    find_probe_rows,
    read_selected_chunks,
    read_selected_works,
)

DEFAULT_WORKS = RETRIEVAL_CORPUS_ROOT / "werneror_works.jsonl"


class SummaryProbeChunk(TypedDict):
    text: str


class SummaryProbe(TypedDict):
    rank: int
    cosine: float
    chunk: SummaryProbeChunk


_SUMMARY_PROBES_ADAPTER = TypeAdapter(list[SummaryProbe])


CHUNK_PATHS = {
    "sentence": RETRIEVAL_CORPUS_ROOT / "werneror_chunks_sentence.jsonl",
    "clause": RETRIEVAL_CORPUS_ROOT / "werneror_chunks_clause.jsonl",
}


def resolve_chunk_path(manifest: Mapping[str, object], requested_path: Path | None) -> Path:
    if requested_path is not None:
        return requested_path.expanduser().resolve()
    policy = manifest["chunk_policy"]
    if not isinstance(policy, str) or policy not in CHUNK_PATHS:
        raise ValueError(f"尚不支持该 chunk_policy：{policy!r}")
    return CHUNK_PATHS[policy].resolve()


def resolve_query_model_path(
    manifest: Mapping[str, object],
    requested_path: Path | None,
) -> Path:
    if requested_path is not None:
        return requested_path.expanduser().resolve()

    if manifest["model"] == QWEN_MODEL:
        fingerprint = manifest["model_fingerprint"]
        if not isinstance(fingerprint, str):
            raise ValueError("manifest model_fingerprint 必须是字符串")
        return (
            DEFAULT_MODEL_ROOT
            / f"Qwen3-Embedding-0.6B-{fingerprint[:12]}"
        ).resolve()

    if manifest["model"] == BERT_CCPOEM_MODEL:
        return (DEFAULT_MODEL_ROOT / "BERT_CCPoem_v1").resolve()

    raise ValueError(f"尚不支持该 Embedding model：{manifest['model']!r}")


def encode_qwen_query(
    *,
    query: str,
    model_path: Path,
    manifest: ArtifactManifest,
    device: str | None,
):
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError(
            "Qwen Retrieval 需要 sentence-transformers；"
            "请安装 requirements-retrieval.txt"
        ) from exc

    ensure_model_snapshot(
        model_path,
        manifest["model_fingerprint"],
    )

    model = SentenceTransformer(
        str(model_path), local_files_only=True, device=device
    )
    dimension = manifest["embedding_dimension"]
    vectors = model.encode(
        [query],
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
        truncate_dim=dimension,
    )
    if vectors.shape != (1, dimension):
        raise RuntimeError(
            f"Query Embedding shape={vectors.shape}，预期 {(1, dimension)}"
        )
    return vectors[0], str(model.device)


def encode_bert_ccpoem_query(
    *,
    query: str,
    model_path: Path,
    manifest: ArtifactManifest,
    device: str | None,
):
    try:
        import torch
        from transformers import AutoModel, BertModel, BertTokenizer
    except ImportError as exc:
        raise RuntimeError(
            "BERT-CCPoem Retrieval 需要 torch / transformers；"
            "请安装 requirements-retrieval.txt"
        ) from exc

    from scripts.corpus.bert_ccpoem_embedding_build import (
        encode_batch,
        fingerprint_model_dir,
    )

    if not model_path.is_dir():
        raise ValueError(
            "本地缺少 BERT-CCPoem 模型目录："
            f"{model_path}；请用 --model-path 指定 BERT_CCPoem_v1"
        )

    actual_fingerprint = fingerprint_model_dir(model_path)
    expected_fingerprint = manifest["model_fingerprint"]
    if actual_fingerprint != expected_fingerprint:
        raise ValueError(
            "本地 BERT-CCPoem 与生成 Corpus Embedding 的模型不一致。\n"
            f"manifest={expected_fingerprint}\n"
            f"local={actual_fingerprint}\n"
            f"path={model_path}"
        )

    selected_device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    tokenizer = BertTokenizer.from_pretrained(
        str(model_path),
        local_files_only=True,
    )
    model = AutoModel.from_pretrained(
        str(model_path), local_files_only=True
    )
    if not isinstance(model, BertModel):
        raise ValueError("BERT-CCPoem 模型配置必须对应 BertModel")
    torch.nn.Module.to(model, device=torch.device(selected_device))
    model.eval()

    vectors = encode_batch(
        [query],
        tokenizer,
        model,
        selected_device,
        torch,
    )
    dimension = manifest["embedding_dimension"]
    if vectors.shape != (1, dimension):
        raise RuntimeError(
            f"Query Embedding shape={vectors.shape}，预期 {(1, dimension)}"
        )
    return vectors[0], selected_device


def encode_query_for_artifact(
    *,
    query: str,
    model_path: Path,
    manifest: ArtifactManifest,
    device: str | None,
):
    if manifest["model"] == QWEN_MODEL:
        return encode_qwen_query(
            query=query,
            model_path=model_path,
            manifest=manifest,
            device=device,
        )
    if manifest["model"] == BERT_CCPOEM_MODEL:
        return encode_bert_ccpoem_query(
            query=query,
            model_path=model_path,
            manifest=manifest,
            device=device,
        )
    raise ValueError(f"尚不支持该 Embedding model：{manifest['model']!r}")


def run_artifact_search(
    *,
    query: str,
    artifact_dir: Path,
    work_path: Path = DEFAULT_WORKS,
    chunk_path: Path | None = None,
    model_path: Path | None = None,
    top_k: int = DEFAULT_TOP_K,
    before_dynasty: str | None = None,
    probe_text: str | None = None,
    probe_author: str | None = None,
    device: str | None = None,
    verify_input_hash: bool = False,
) -> dict[str, object]:
    if top_k <= 0:
        raise ValueError("top_k 必须为正整数")
    if probe_author and not probe_text:
        raise ValueError("probe_author 必须和 probe_text 一起使用")

    artifact_dir = artifact_dir.expanduser().resolve()
    work_path = work_path.expanduser().resolve()
    manifest = load_artifact_manifest(artifact_dir)
    chunk_path = resolve_chunk_path(manifest, chunk_path)
    model_path = resolve_query_model_path(manifest, model_path)

    if verify_input_hash:
        if not chunk_path.is_file():
            raise ValueError(f"Chunk JSONL 不存在：{chunk_path}")
        actual_hash = sha256_file(chunk_path)
        if actual_hash != manifest.get("input_sha256"):
            raise ValueError(
                "Chunk JSONL SHA256 与 Embedding manifest 不一致；"
                "不能把这些向量映射到当前 Chunk 文件。\n"
                f"manifest={manifest.get('input_sha256')}\n"
                f"actual={actual_hash}"
            )

    chronology = None
    row_mask = None
    if before_dynasty:
        allowed_dynasties = candidate_prior_dynasties(before_dynasty)
        row_mask = build_dynasty_row_mask(
            work_path=work_path,
            chunk_path=chunk_path,
            allowed_dynasties=allowed_dynasties,
            expected_chunks=manifest["completed_chunks"],
        )
        eligible_shards = sum(
            bool(row_mask[item["start"]:item["end"]].any())
            for item in manifest["completed_shards"]
        )
        chronology = {
            "before_dynasty": before_dynasty,
            "allowed_dynasties": sorted(allowed_dynasties),
            "eligible_chunks": int(row_mask.sum()),
            "eligible_shards": eligible_shards,
            "total_shards": len(manifest["completed_shards"]),
        }
        if chronology["eligible_chunks"] == 0:
            raise ValueError("朝代过滤后没有可检索的 Chunk")

    probe_rows: set[int] = set()
    if probe_text:
        probe_rows = find_probe_rows(
            work_path=work_path,
            chunk_path=chunk_path,
            probe_text=probe_text,
            probe_author=probe_author,
        )
        if not probe_rows:
            raise ValueError(
                "没有找到符合 probe 条件的 Chunk："
                f"text={probe_text!r}, author={probe_author!r}"
            )

    query_vector, selected_device = encode_query_for_artifact(
        query=query,
        model_path=model_path,
        manifest=manifest,
        device=device,
    )

    ranking, probe_stats = exact_search(
        artifact_dir=artifact_dir,
        manifest=manifest,
        query_vector=query_vector,
        top_k=top_k,
        row_mask=row_mask,
        probe_rows=probe_rows,
    )

    selected_rows = {
        row_id for _, row_id in ranking
    } | set(probe_stats)
    chunks = read_selected_chunks(chunk_path, selected_rows)
    works = read_selected_works(
        work_path,
        [chunks[row_id]["work_id"] for row_id in selected_rows],
    )

    probe_results = []
    for row_id, stats in sorted(
        probe_stats.items(),
        key=lambda item: (item[1]["rank"], item[0]),
    ):
        chunk = chunks[row_id]
        work = works[chunk["work_id"]]
        probe_results.append(
            {
                **stats,
                "global_row": row_id,
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
        "query": query,
        "model": manifest["model"],
        "chunk_policy": manifest["chunk_policy"],
        "device": selected_device,
        "dimension": manifest["embedding_dimension"],
        "corpus_chunks": manifest["completed_chunks"],
        "top_k": top_k,
        "chronology_filter": chronology,
        "ranking": build_result_rows(ranking, chunks, works),
        "probes": probe_results,
        "note": "Exact Retrieval 只负责候选召回；相似度不是文学关系判定。",
    }


def summarize_result(label: str, result: Mapping[str, object]) -> dict[str, object]:
    """Compact an Artifact search into an interpretable target-rank summary."""
    probes = _SUMMARY_PROBES_ADAPTER.validate_python(result.get("probes") or [])
    best = min(probes, key=lambda item: item["rank"]) if probes else None
    return {
        "label": label,
        "model": result["model"],
        "chunk_policy": result["chunk_policy"],
        "dimension": result["dimension"],
        "corpus_chunks": result["corpus_chunks"],
        "best_probe_rank": best["rank"] if best else None,
        "best_probe_cosine": best["cosine"] if best else None,
        "probe_matches": len(probes),
        "best_probe_text": best["chunk"]["text"] if best else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="按 Artifact manifest 自动选择编码器的 Exact Retrieval"
    )
    parser.add_argument("query", help="要检索的当前诗句或片段")
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--chunks", type=Path)
    parser.add_argument("--works", type=Path, default=DEFAULT_WORKS)
    parser.add_argument("--model-path", type=Path)
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--before-dynasty")
    parser.add_argument("--probe-text")
    parser.add_argument("--probe-author")
    parser.add_argument("--device")
    parser.add_argument("--verify-input-hash", action="store_true")
    parser.add_argument("--summary", action="store_true",
                        help="只输出目标匹配的名次与最相近片段摘要")
    args = parser.parse_args()

    try:
        result = run_artifact_search(
            query=args.query,
            artifact_dir=args.artifact_dir,
            work_path=args.works,
            chunk_path=args.chunks,
            model_path=args.model_path,
            top_k=args.top_k,
            before_dynasty=args.before_dynasty,
            probe_text=args.probe_text,
            probe_author=args.probe_author,
            device=args.device,
            verify_input_hash=args.verify_input_hash,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    payload = summarize_result(args.artifact_dir.name, result) if args.summary else result
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
