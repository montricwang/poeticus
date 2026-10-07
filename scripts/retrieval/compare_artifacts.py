"""Compare the same known Retrieval relation across three Artifacts.

Default matrix:
- Qwen + sentence + 1024d
- Qwen + clause + 1024d
- BERT-CCPoem + clause + 512d

The runner reports the best known-target rank for each Artifact. It is a
diagnostic comparison, not a production benchmark harness.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.retrieval.artifact_search import (
    BERT_CCPOEM_MODEL,
    QWEN_MODEL,
    run_artifact_search,
)

DEFAULT_DATA_ROOT = Path("../poeticus-data/output/retrieval")
DEFAULT_WORKS = DEFAULT_DATA_ROOT / "werneror_works.jsonl"
DEFAULT_QWEN_SENTENCE = (
    DEFAULT_DATA_ROOT / "embeddings/qwen3_0.6b_sentence_1024"
)
DEFAULT_QWEN_CLAUSE = (
    DEFAULT_DATA_ROOT / "embeddings/qwen3_0.6b_clause_1024"
)
DEFAULT_BERT_CLAUSE = (
    DEFAULT_DATA_ROOT / "embeddings/bert_ccpoem_clause_512"
)


def summarize_result(label: str, result: dict) -> dict:
    probes = result.get("probes") or []
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
        description="横向比较 sentence-Qwen / clause-Qwen / clause-BERT"
    )
    parser.add_argument("query")
    parser.add_argument("--probe-text", required=True)
    parser.add_argument("--probe-author")
    parser.add_argument("--before-dynasty")
    parser.add_argument("--works", type=Path, default=DEFAULT_WORKS)
    parser.add_argument(
        "--qwen-sentence-artifact",
        type=Path,
        default=DEFAULT_QWEN_SENTENCE,
    )
    parser.add_argument(
        "--qwen-clause-artifact",
        type=Path,
        default=DEFAULT_QWEN_CLAUSE,
    )
    parser.add_argument(
        "--bert-clause-artifact",
        type=Path,
        default=DEFAULT_BERT_CLAUSE,
    )
    parser.add_argument(
        "--qwen-model-path",
        type=Path,
        help="可选：两套 Qwen Artifact 共用的本地模型目录",
    )
    parser.add_argument(
        "--bert-model-path",
        type=Path,
        help="可选：BERT_CCPoem_v1 本地模型目录",
    )
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--device")
    args = parser.parse_args()

    specs = [
        (
            "qwen_sentence_1024",
            args.qwen_sentence_artifact,
            args.qwen_model_path,
            QWEN_MODEL,
        ),
        (
            "qwen_clause_1024",
            args.qwen_clause_artifact,
            args.qwen_model_path,
            QWEN_MODEL,
        ),
        (
            "bert_ccpoem_clause_512",
            args.bert_clause_artifact,
            args.bert_model_path,
            BERT_CCPOEM_MODEL,
        ),
    ]

    comparison = []
    details = {}
    for label, artifact_dir, model_path, expected_model in specs:
        print(f"=== {label} ===", flush=True)
        result = run_artifact_search(
            query=args.query,
            artifact_dir=artifact_dir,
            work_path=args.works,
            model_path=model_path,
            top_k=args.top_k,
            before_dynasty=args.before_dynasty,
            probe_text=args.probe_text,
            probe_author=args.probe_author,
            device=args.device,
        )
        if result["model"] != expected_model:
            raise SystemExit(
                f"{label} 的 Artifact model={result['model']!r}，"
                f"预期 {expected_model!r}"
            )
        comparison.append(summarize_result(label, result))
        details[label] = {
            "chronology_filter": result["chronology_filter"],
            "probes": result["probes"],
            "ranking": result["ranking"],
        }

    payload = {
        "query": args.query,
        "probe_text": args.probe_text,
        "probe_author": args.probe_author,
        "before_dynasty": args.before_dynasty,
        "comparison": comparison,
        "details": details,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
