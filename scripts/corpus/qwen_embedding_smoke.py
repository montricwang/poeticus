"""Minimal local smoke test for Qwen3 Embedding.

Purpose:
- let Hugging Face / sentence-transformers download the model on first run;
- confirm Poeticus can turn classical Chinese lines into embeddings;
- show vector dimension and cosine similarities on a tiny example.

This is NOT the retrieval benchmark and never reads the 4.8M chunk corpus.

Install the optional local dependency first:

    pip install -r requirements-retrieval.txt

Then run with Hugging Face model id:

    python -m scripts.corpus.qwen_embedding_smoke

Or point at a complete local snapshot downloaded from ModelScope / Hugging Face:

    python -m scripts.corpus.qwen_embedding_smoke --model-path D:\\models\\Qwen3-Embedding-0.6B
"""
from __future__ import annotations

import argparse
import json
import math
from collections.abc import Sequence
from pathlib import Path

MODEL_NAME = "Qwen/Qwen3-Embedding-0.6B"

QUERY = "客舍青青，特地添明秀。"
CANDIDATES = (
    "渭城朝雨浥轻尘，客舍青青柳色新。",
    "大漠孤烟直，长河落日圆。",
    "海上生明月，天涯共此时。",
)


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise ValueError("向量维度不一致")
    if not left:
        raise ValueError("不能比较空向量")

    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        raise ValueError("不能比较零向量")
    return dot / (left_norm * right_norm)


def rank_candidates(
    query_vector: Sequence[float],
    candidate_vectors: Sequence[Sequence[float]],
    candidate_texts: Sequence[str],
) -> list[dict]:
    if len(candidate_vectors) != len(candidate_texts):
        raise ValueError("候选文本与候选向量数量不一致")

    rows = [
        {
            "text": text,
            "cosine": cosine_similarity(query_vector, vector),
        }
        for text, vector in zip(candidate_texts, candidate_vectors)
    ]
    rows.sort(key=lambda row: row["cosine"], reverse=True)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Qwen3-Embedding-0.6B 本地最小 smoke test"
    )
    parser.add_argument(
        "--device",
        help="可选：显式指定 cpu / cuda / mps；默认交给 sentence-transformers",
    )
    parser.add_argument(
        "--model-path",
        type=Path,
        help=(
            "可选：完整本地模型目录。指定后强制 local_files_only，"
            "不会访问 Hugging Face。"
        ),
    )
    args = parser.parse_args()

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise SystemExit(
            "尚未安装 Retrieval 依赖。请先运行："
            "pip install -r requirements-retrieval.txt"
        ) from exc

    kwargs = {}
    if args.device:
        kwargs["device"] = args.device

    if args.model_path:
        model_path = args.model_path.expanduser().resolve()
        if not model_path.is_dir():
            raise SystemExit(f"本地模型目录不存在：{model_path}")
        required = ("config.json", "model.safetensors", "tokenizer_config.json")
        missing = [name for name in required if not (model_path / name).is_file()]
        if missing:
            raise SystemExit(
                "本地模型目录不完整，缺少：" + ", ".join(missing)
            )
        model_source = str(model_path)
        kwargs["local_files_only"] = True
        print(f"只从本地加载模型：{model_source}", flush=True)
    else:
        model_source = MODEL_NAME
        print(
            f"加载 {MODEL_NAME}；首次运行会由 Hugging Face 自动下载模型……",
            flush=True,
        )

    model = SentenceTransformer(model_source, **kwargs)

    texts = [QUERY, *CANDIDATES]
    embeddings = model.encode(
        texts,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    if len(embeddings.shape) != 2 or embeddings.shape[0] != len(texts):
        raise RuntimeError(f"Embedding 输出形状异常：{embeddings.shape}")

    query_vector = embeddings[0].tolist()
    candidate_vectors = [row.tolist() for row in embeddings[1:]]
    ranking = rank_candidates(query_vector, candidate_vectors, CANDIDATES)

    result = {
        "model": MODEL_NAME,
        "model_source": model_source,
        "device": str(model.device),
        "texts": len(texts),
        "embedding_dimension": int(embeddings.shape[1]),
        "query": QUERY,
        "query_vector_head": [
            round(float(value), 6) for value in embeddings[0][:8]
        ],
        "ranking": [
            {
                "rank": rank,
                "text": row["text"],
                "cosine": round(row["cosine"], 6),
            }
            for rank, row in enumerate(ranking, 1)
        ],
        "note": (
            "这里只验证 Embedding 链路和基本相似度直觉；"
            "不是 Poeticus Retrieval 质量评测。"
        ),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
