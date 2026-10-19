"""对同一 Document Corpus 执行 Qwen Dense 与 BM25+Dense RRF 离线对照（#133）。

不修改已有 Poem Retrieval，默认只使用 Seed Eval 的 development/in_corpus 问题。
文献向量按固定批次缓存在相邻 poeticus-data 内，可多次运行逐批构建。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from backend.data_paths import DATA_ROOT, MODELS_ROOT
from scripts.experiments.document_rag_lexical_baseline import (
    DEFAULT_CASES,
    DEFAULT_CORPUS,
    SectionBM25,
    checked_cases,
    checked_sections,
    grade_case,
    section_key,
)

MODEL_ID = "Qwen/Qwen3-Embedding-0.6B"
DEFAULT_MODEL = MODELS_ROOT / "Qwen3-Embedding-0.6B-7c0e29cfcdf2"
DEFAULT_CACHE = DATA_ROOT / "document-corpus/embeddings/qwen3_0.6b_sections_v01"
DEFAULT_REPORT = DATA_ROOT / "document-corpus/evals/results/document_retrieval_comparison_v0.1.json"
RRF_CONSTANT = 60
CANDIDATE_DEPTH = 50
MAX_TOKENS = 512
BATCH_SIZE = 16


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def section_text(section: dict[str, Any]) -> str:
    """两个通道使用完全相同的标题和正文，不追加已知目标书名。"""
    return f"{section['title']} {section['text']}"


def cache_spec(corpus: Path, model_path: Path, n: int, batch_size: int, max_tokens: int) -> dict[str, Any]:
    config = model_path / "config_sentence_transformers.json"
    if not config.is_file():
        raise FileNotFoundError(f"Embedding 模型缺少 prompts 配置：{config}")
    prompts = json.loads(config.read_text(encoding="utf-8"))["prompts"]
    if "query" not in prompts or "document" not in prompts:
        raise ValueError("预期模型具有 query/document prompts")
    return {
        "corpus_sha256": sha256(corpus),
        "model_id": MODEL_ID,
        "model_snapshot": str(model_path.resolve()),
        "model_prompt_config_sha256": sha256(config),
        "query_prompt": prompts["query"],
        "document_prompt": prompts["document"],
        "max_seq_length": max_tokens,
        "batch_size": batch_size,
        "sections": n,
        "dimension": 1024,
        "normalize_embeddings": True,
    }


def read_or_create_spec(cache: Path, expected: dict[str, Any]) -> None:
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / "spec.json"
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing != expected:
            raise ValueError("缓存配置与语料或模型不一致；请使用新的 --cache 路径，不要复用旧向量")
        return
    if list(cache.glob("batch_*.npy")):
        raise ValueError("目录存在没有 spec.json 的 Embedding 分片，拒绝混用")
    path.write_text(json.dumps(expected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def valid_batch(path: Path, rows: int, dimension: int) -> bool:
    if not path.is_file():
        return False
    vectors = np.load(path, allow_pickle=False)
    if vectors.shape != (rows, dimension) or not np.isfinite(vectors).all():
        raise ValueError(f"向量分片损坏或形状不符: {path}")
    return True


def load_model(model_path: Path, max_tokens: int) -> Any:
    from sentence_transformers import SentenceTransformer

    if not model_path.is_dir():
        raise FileNotFoundError(f"找不到本地模型：{model_path}")
    model = SentenceTransformer(str(model_path), local_files_only=True, device="cpu")
    model.max_seq_length = max_tokens
    return model


def get_document_vectors(
    sections: list[dict[str, Any]],
    *,
    model_path: Path,
    cache: Path,
    spec: dict[str, Any],
    max_new_batches: int,
) -> tuple[NDArray[np.float32] | None, Any | None]:
    """按可复核的批次缓存；限制批次数时可以安全地继续下一次运行。"""
    read_or_create_spec(cache, spec)
    batch_size = spec["batch_size"]
    dimension = spec["dimension"]
    count = math.ceil(len(sections) / batch_size)
    paths = [cache / f"batch_{index:04d}.npy" for index in range(count)]
    needed = [
        index
        for index, path in enumerate(paths)
        if not valid_batch(path, min(batch_size, len(sections) - index * batch_size), dimension)
    ]
    model = None
    new_batches = 0
    if needed:
        model = load_model(model_path, spec["max_seq_length"])
        for index in needed:
            if max_new_batches and new_batches >= max_new_batches:
                break
            start = index * batch_size
            texts = [section_text(s) for s in sections[start:start + batch_size]]
            vectors = model.encode(
                texts,
                prompt_name="document",
                # CPU 同机仍运行 Poem Retrieval；少量长 Section 不宜在 16 条一批里一起补齐到 512 tokens。
                batch_size=min(batch_size, 2),
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
            matrix = np.asarray(vectors, dtype=np.float32)
            if matrix.shape != (len(texts), dimension) or not np.isfinite(matrix).all():
                raise ValueError(f"Embedding 返回非法 shape/数值: batch={index} shape={matrix.shape}")
            path = paths[index]
            temporary = path.with_suffix(".tmp")
            with temporary.open("wb") as stream:
                np.save(stream, matrix, allow_pickle=False)
            temporary.replace(path)
            new_batches += 1
            print(f"Encoded sections {min(start + len(texts), len(sections))}/{len(sections)}", flush=True)
    completed = sum(valid_batch(p, min(batch_size, len(sections) - i * batch_size), dimension) for i, p in enumerate(paths))
    if completed < count:
        print(f"Document vectors {completed}/{count} batches cached; rerun the same command to continue", flush=True)
        return None, None
    matrix = np.concatenate([np.load(path, allow_pickle=False) for path in paths]).astype(np.float32, copy=False)
    if matrix.shape != (len(sections), dimension):
        raise ValueError("文献向量数量与语料顺序不一致")
    return matrix, model


def fuse_rrf(
    lexical: list[tuple[str, float]],
    dense: list[tuple[str, float]],
    k: int,
    *,
    constant: int = RRF_CONSTANT,
) -> list[tuple[str, float]]:
    """Rank-based 融合，不混用 BM25 与余弦相似度的数值尺度。"""
    scores: dict[str, float] = {}
    for channel in (lexical, dense):
        for index, (key, _score) in enumerate(channel):
            scores[key] = scores.get(key, 0.0) + 1 / (constant + index + 1)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:k]


def summary(results: list[dict[str, Any]]) -> dict[str, float | int]:
    return {
        "cases": len(results),
        "hit_at_5": round(sum(r["hit_at_k"] for r in results) / len(results), 4),
        "all_gold_at_5": round(sum(r["all_gold_at_k"] for r in results) / len(results), 4),
        "mean_recall_at_5": round(sum(r["recall_at_k"] for r in results) / len(results), 4),
        "mrr_at_5": round(sum(r["reciprocal_rank"] for r in results) / len(results), 4),
    }


def run(
    *,
    corpus: Path = DEFAULT_CORPUS,
    cases_path: Path = DEFAULT_CASES,
    model_path: Path = DEFAULT_MODEL,
    cache: Path = DEFAULT_CACHE,
    report: Path = DEFAULT_REPORT,
    max_new_batches: int = 0,
    batch_size: int = BATCH_SIZE,
    max_tokens: int = MAX_TOKENS,
) -> dict[str, Any] | None:
    if batch_size < 1 or max_tokens < 16 or max_new_batches < 0:
        raise ValueError("batch_size / max_tokens / max_new_batches 无效")
    sections = checked_sections(corpus)
    cases = checked_cases(cases_path, sections)
    development = [c for c in cases if c["split"] == "development" and c["gold_status"] == "gold_checked" and c["local_coverage"] == "in_corpus"]
    if not development:
        raise ValueError("没有 development / in_corpus 已核对题目")
    spec = cache_spec(corpus, model_path, len(sections), batch_size, max_tokens)
    started = time.perf_counter()
    documents, model = get_document_vectors(
        sections, model_path=model_path, cache=cache, spec=spec, max_new_batches=max_new_batches,
    )
    encoding_seconds = time.perf_counter() - started
    if documents is None:
        return None
    if model is None:
        model = load_model(model_path, max_tokens)
    questions = [c["question"] for c in development]
    started = time.perf_counter()
    q_vectors = np.asarray(model.encode(
        questions, prompt_name="query", batch_size=batch_size,
        normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False,
    ), dtype=np.float32)
    query_encoding_seconds = time.perf_counter() - started
    if q_vectors.shape != (len(development), spec["dimension"]):
        raise ValueError("Query Embedding 维度不符")
    similarities = q_vectors @ documents.T
    keys = [section_key(s) for s in sections]
    lexical_search = SectionBM25(sections)
    records: list[dict[str, Any]] = []
    started = time.perf_counter()
    for case, sims in zip(development, similarities, strict=True):
        bm25 = lexical_search.search(case["question"], CANDIDATE_DEPTH)
        indices = np.argsort(-sims, kind="stable")[:CANDIDATE_DEPTH]
        dense = sorted(
            ((keys[int(i)], float(sims[int(i)])) for i in indices),
            key=lambda item: (-item[1], item[0]),
        )
        fused = fuse_rrf(bm25, dense, 5)
        grades = {
            "bm25": grade_case(case, bm25[:5], 5),
            "dense": grade_case(case, dense[:5], 5),
            "hybrid": grade_case(case, fused, 5),
        }
        records.append({"case_id": case["id"], "question": case["question"], "grades": grades})
    ranking_seconds = time.perf_counter() - started
    summary_by_method = {method: summary([r["grades"][method] for r in records]) for method in ("bm25", "dense", "hybrid")}
    result = {
        "experiment": "document_rag_qwen_dense_rrf_v0.1",
        "scope": "development_in_corpus_only",
        "inputs": {
            "corpus": str(corpus.resolve()),
            "corpus_sha256": spec["corpus_sha256"],
            "cases": str(cases_path.resolve()),
            "cases_sha256": sha256(cases_path),
            "total_sections": len(sections),
            "development_cases": len(development),
        },
        "dense": spec,
        "fusion": {"algorithm": "RRF", "rrf_constant": RRF_CONSTANT, "candidate_depth_each": CANDIDATE_DEPTH, "final_k": 5},
        "bm25": {"tokenizer": "NFKC char 2-3gram", "search_fields": ["title", "text"], "query": "question as written"},
        "timing_seconds": {
            "cache_or_document_encoding": round(encoding_seconds, 3),
            "query_encoding": round(query_encoding_seconds, 3),
            "ranking": round(ranking_seconds, 3),
        },
        "summary": summary_by_method,
        "results": records,
        "limitations": [
            "仅比较 Retriever，尚未做 Context Construction / LLM 回答",
            "Gold 引文对齐不代表原文版本已校勘",
            "仅对长 Section 做 token 上限截断；可能丢失后部内容",
            "仅运行开发题，未碰 holdout 题",
            "未做简繁字归一化、别名扩展、调参或 Rerank",
        ],
    }
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary_by_method, ensure_ascii=False, indent=2))
    print(f"Report: {report}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    parser.add_argument("--max-tokens", type=int, default=MAX_TOKENS)
    parser.add_argument("--max-new-batches", type=int, default=0, help="分批逐次编码时每轮最多追加多少批；0 为不限制")
    args = parser.parse_args()
    run(
        corpus=args.corpus, cases_path=args.cases, model_path=args.model,
        cache=args.cache, report=args.output, batch_size=args.batch_size,
        max_tokens=args.max_tokens, max_new_batches=args.max_new_batches,
    )


if __name__ == "__main__":
    main()
