"""Document RAG Reranker A/B: frozen development queries, no Agent/tool changes.

A=current early Top5 per query, B=delayed TopK, C=B's candidates reordered
by Qwen3 causal-LM reranker. Existing Gold is only used for reporting.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from backend.data_paths import DATA_ROOT
from scripts.experiments.document_rag_answers import LocalHybrid, load_development
from scripts.experiments.document_rag_dense_hybrid import (
    DEFAULT_CORPUS, DEFAULT_MODEL, DEFAULT_CACHE, RRF_CONSTANT, CANDIDATE_DEPTH,
)
from scripts.experiments.document_rag_lexical_baseline import DEFAULT_CASES
from scripts.experiments.document_reranker_model import Qwen3Reranker, MODEL_PATH

FROZEN = DATA_ROOT / "document-corpus/evals/results/document_rag_answers_v0.1.json"
REPORT = DATA_ROOT / "document-corpus/evals/results/document_reranker_comparison_v0.1.json"


def rrf(channels: list[list[str]], k: int) -> list[str]:
    scores: dict[str, float] = {}
    for channel in channels:
        for i, key in enumerate(channel, 1):
            scores[key] = scores.get(key, 0.0) + 1 / (RRF_CONSTANT + i)
    return sorted(scores, key=lambda key: (-scores[key], key))[:k]


def hybrid(engine: LocalHybrid, query: str) -> list[str]:
    v = np.asarray(engine.model.encode(
        [query], prompt_name="query", batch_size=1,
        normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False,
    ), dtype=np.float32)[0]
    scores = v @ engine.vectors.T
    order = np.argsort(-scores, kind="stable")[:CANDIDATE_DEPTH]
    lexical = [key for key, _ in engine.bm25.search(query, CANDIDATE_DEPTH)]
    dense = [engine.keys[int(index)] for index in order]
    return rrf([lexical, dense], CANDIDATE_DEPTH * 2)


def grade(keys: list[str], gold: set[str]) -> dict[str, object]:
    matched = gold & set(keys)
    first = next((i for i, key in enumerate(keys, 1) if key in gold), None)
    return {
        "keys": keys, "hits": len(matched), "gold_total": len(gold),
        "recall": len(matched) / len(gold), "hit": bool(matched),
        "all_gold": matched == gold, "rr": 1 / first if first else 0.0,
    }


def evaluate(cases: list[dict], engine: LocalHybrid, reranker: Qwen3Reranker | None, pool_size: int) -> list[dict]:
    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))["cases"]
    records = []
    for case in cases:
        start = time.perf_counter()
        name, question = case["id"], case["question"]
        queries = frozen[name]["modes"]["agentic_hybrid"]["queries"]
        if queries[0] != question:
            raise ValueError(f"Frozen Query mismatch: {name}")
        ranks = [hybrid(engine, query) for query in queries]
        old = rrf([r[:5] for r in ranks], 5)
        pool = rrf([r[:50] for r in ranks], pool_size)
        delayed = pool[:5]
        reranked = None
        raw_scores = None
        if reranker:
            texts = [
                engine.sections[key]["title"] + " " + engine.sections[key]["text"][:900]
                for key in pool
            ]
            raw_scores = reranker.score(question, texts)
            reranked = [key for _, key in sorted(zip(raw_scores, pool),
                           key=lambda x: (-x[0], x[1]))][:5]
        gold = {"|".join((g["document"], g["epub_xhtml"], str(g["epub_section_id"])))
                for g in case["gold_evidence"]}
        record = {
            "case_id": name, "question": question, "queries": queries,
            "gold": sorted(gold), "pool": pool, "raw_scores": raw_scores,
            "pool_gold_hits": len(set(pool) & gold),
            "old": grade(old, gold), "delayed": grade(delayed, gold),
            "reranked": grade(reranked, gold) if reranked is not None else None,
            "seconds": round(time.perf_counter()-start, 2),
        }
        records.append(record)
        print(name, "gold", len(gold), "pool", record["pool_gold_hits"],
              "old", record["old"]["hits"], "delayed", record["delayed"]["hits"],
              "rerank", record["reranked"]["hits"] if record["reranked"] else "-",
              "seconds", record["seconds"], flush=True)
    return records


def summarize(records: list[dict], key: str) -> dict | None:
    rows = [r[key] for r in records]
    if any(item is None for item in rows):
        return None
    return {
        "n": len(rows),
        "hit@5": round(sum(bool(r["hit"]) for r in rows) / len(rows), 4),
        "all_gold@5": round(sum(bool(r["all_gold"]) for r in rows) / len(rows), 4),
        "recall@5": round(sum(float(r["recall"]) for r in rows) / len(rows), 4),
        "mrr@5": round(sum(float(r["rr"]) for r in rows) / len(rows), 4),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", nargs="*")
    parser.add_argument("--pool", type=int, default=20)
    parser.add_argument("--no-reranker", action="store_true")
    parser.add_argument("--report", type=Path, default=REPORT)
    args = parser.parse_args()
    if not 5 <= args.pool <= 50:
        parser.error("--pool must be 5..50")
    sections, cases = load_development(DEFAULT_CORPUS, DEFAULT_CASES)
    cases = [c for c in cases if not args.cases or c["id"] in args.cases]
    if args.cases and len(cases) != len(set(args.cases)):
        parser.error("not all requested cases are development/in_corpus")
    engine = LocalHybrid(DEFAULT_CORPUS, sections, model_path=DEFAULT_MODEL, cache=DEFAULT_CACHE)
    reranker = None if args.no_reranker else Qwen3Reranker()
    start = time.perf_counter()
    records = evaluate(cases, engine, reranker, args.pool)
    summary = {name: summarize(records, name) for name in ("old", "delayed", "reranked")}
    report = {
        "scope": "development/in_corpus only; no Gold used in ranking",
        "frozen_queries": str(FROZEN), "reranker_model": str(MODEL_PATH) if reranker else None,
        "pool": args.pool, "token_budget": 512, "seconds": round(time.perf_counter()-start, 2),
        "note": "Local cached embedding dot product; pgvector uses cosine; slight score differences expected.",
        "summary": summary, "cases": records,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("SUMMARY", json.dumps(summary,ensure_ascii=False), "TOTAL_SECONDS", report["seconds"], flush=True)


if __name__ == "__main__":
    main()
