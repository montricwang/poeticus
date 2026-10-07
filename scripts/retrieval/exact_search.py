"""Exact full-corpus retrieval over Qwen embedding shards.

This is a diagnostic baseline, not the production ANN/index implementation.

Pipeline:

    query text
        -> Qwen3-Embedding-0.6B query embedding
        -> exact dot product against every normalized corpus vector
        -> global Top-K
        -> recover Chunk rows and parent Work metadata

Run from the Poeticus repository root. By default, large local artifacts live
in the sibling poeticus-data directory and are never committed to this repo.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Iterable

MODEL_NAME = "Qwen/Qwen3-Embedding-0.6B"
DEFAULT_DATA_ROOT = Path("../poeticus-data/output/retrieval")
DEFAULT_CHUNKS = DEFAULT_DATA_ROOT / "werneror_chunks_sentence.jsonl"
DEFAULT_WORKS = DEFAULT_DATA_ROOT / "werneror_works.jsonl"
DEFAULT_ARTIFACT_DIR = (
    DEFAULT_DATA_ROOT / "embeddings/qwen3_0.6b_sentence_1024"
)
DEFAULT_TOP_K = 20


def sha256_file(path: Path, block_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(block_size):
            digest.update(block)
    return digest.hexdigest()


def load_manifest(artifact_dir: Path) -> dict:
    manifest_path = artifact_dir / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError(f"Embedding manifest 不存在：{manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "complete":
        raise ValueError(
            f"Embedding Artifact 尚未完成：status={manifest.get('status')!r}"
        )
    if manifest.get("model") != MODEL_NAME:
        raise ValueError(
            f"Embedding model={manifest.get('model')!r}，预期 {MODEL_NAME!r}"
        )

    dimension = manifest.get("embedding_dimension")
    completed_chunks = manifest.get("completed_chunks")
    shards = manifest.get("completed_shards")

    if not isinstance(dimension, int) or dimension <= 0:
        raise ValueError("manifest 缺少有效 embedding_dimension")
    if not isinstance(completed_chunks, int) or completed_chunks <= 0:
        raise ValueError("manifest 缺少有效 completed_chunks")
    if not isinstance(shards, list) or not shards:
        raise ValueError("manifest 缺少 completed_shards")

    expected_start = 0
    for item in shards:
        start = item.get("start")
        end = item.get("end")
        filename = item.get("file")
        if start != expected_start or not isinstance(end, int) or end <= start:
            raise ValueError("manifest 中 completed_shards 不是连续区间")
        if not isinstance(filename, str) or not filename:
            raise ValueError("manifest shard 缺少文件名")
        if not (artifact_dir / filename).is_file():
            raise ValueError(f"Embedding shard 不存在：{artifact_dir / filename}")
        expected_start = end

    if expected_start != completed_chunks:
        raise ValueError(
            "manifest 的 completed_chunks 与 completed_shards 范围不一致"
        )

    return manifest


def merge_top_k(
    current: Iterable[tuple[float, int]],
    candidates: Iterable[tuple[float, int]],
    top_k: int,
) -> list[tuple[float, int]]:
    """Merge scored global rows, highest score first, stable on row id."""
    if top_k <= 0:
        raise ValueError("top_k 必须为正整数")
    rows = [*current, *candidates]
    rows.sort(key=lambda item: (-item[0], item[1]))
    return rows[:top_k]


def exact_search(
    artifact_dir: Path,
    manifest: dict,
    query_vector,
    top_k: int,
) -> list[tuple[float, int]]:
    """Scan every shard and return (score, global_row) Top-K."""
    try:
        import numpy as np
    except ImportError as exc:
        raise RuntimeError(
            "Exact Retrieval 需要 NumPy；请安装 requirements-retrieval.txt"
        ) from exc

    dimension = manifest["embedding_dimension"]
    if query_vector.shape != (dimension,):
        raise ValueError(
            f"Query vector shape={query_vector.shape}，预期 {(dimension,)}"
        )

    query = np.asarray(query_vector, dtype=np.float32)
    best: list[tuple[float, int]] = []

    for shard_no, item in enumerate(manifest["completed_shards"], 1):
        path = artifact_dir / item["file"]
        vectors = np.load(path, mmap_mode="r", allow_pickle=False)
        expected_shape = (item["end"] - item["start"], dimension)
        if vectors.shape != expected_shape:
            raise ValueError(
                f"{path.name} shape={vectors.shape}，预期 {expected_shape}"
            )

        # The corpus Artifact is float16 for storage. Exact baseline converts
        # one 10k shard at a time to float32 before the dot product, keeping
        # peak memory bounded while avoiding float16 accumulation as the
        # reference score.
        matrix = np.asarray(vectors, dtype=np.float32)
        scores = matrix @ query

        local_k = min(top_k, scores.shape[0])
        if local_k == scores.shape[0]:
            local_indices = np.arange(scores.shape[0])
        else:
            local_indices = np.argpartition(scores, -local_k)[-local_k:]

        candidates = [
            (float(scores[index]), item["start"] + int(index))
            for index in local_indices
        ]
        best = merge_top_k(best, candidates, top_k)

        print(
            f"Exact search: {shard_no}/{len(manifest['completed_shards'])}",
            end="\r",
            flush=True,
        )

    print(" " * 80, end="\r", flush=True)
    return best


def read_selected_chunks(
    chunk_path: Path,
    row_ids: Iterable[int],
) -> dict[int, dict]:
    """Recover selected logical JSONL rows using the same nonblank-row indexing."""
    wanted = set(row_ids)
    if not wanted:
        return {}
    if min(wanted) < 0:
        raise ValueError("Chunk row id 不能为负数")
    if not chunk_path.is_file():
        raise ValueError(f"Chunk JSONL 不存在：{chunk_path}")

    found: dict[int, dict] = {}
    logical_row = 0
    max_wanted = max(wanted)

    with chunk_path.open(encoding="utf-8") as stream:
        for line_no, line in enumerate(stream, 1):
            if not line.strip():
                continue
            if logical_row in wanted:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"Chunk JSONL 第 {line_no} 行无法解析"
                    ) from exc
                found[logical_row] = record
                if len(found) == len(wanted):
                    break
            if logical_row >= max_wanted:
                break
            logical_row += 1

    missing = sorted(wanted - set(found))
    if missing:
        raise ValueError(f"Chunk JSONL 找不到这些 row：{missing[:10]}")
    return found


def read_selected_works(
    work_path: Path,
    work_ids: Iterable[str],
) -> dict[str, dict]:
    wanted = set(work_ids)
    if not wanted:
        return {}
    if not work_path.is_file():
        raise ValueError(f"Work JSONL 不存在：{work_path}")

    found: dict[str, dict] = {}
    with work_path.open(encoding="utf-8") as stream:
        for line_no, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Work JSONL 第 {line_no} 行无法解析") from exc
            work_id = record.get("work_id")
            if work_id in wanted:
                found[work_id] = record
                if len(found) == len(wanted):
                    break

    missing = sorted(wanted - set(found))
    if missing:
        raise ValueError(f"Work JSONL 找不到这些 work_id：{missing[:10]}")
    return found


def encode_query(
    *,
    query: str,
    model_path: Path,
    dimension: int,
    expected_model_fingerprint: str,
    device: str | None,
):
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError(
            "尚未安装 Retrieval 依赖，请先运行："
            "pip install -r requirements-retrieval.txt"
        ) from exc

    from scripts.corpus.qwen_embedding_build import fingerprint_model_dir

    if not model_path.is_dir():
        raise ValueError(f"本地模型目录不存在：{model_path}")

    actual_fingerprint = fingerprint_model_dir(model_path)
    if actual_fingerprint != expected_model_fingerprint:
        raise ValueError(
            "Query 模型与生成 Corpus Embedding 的模型 fingerprint 不一致；"
            "不要混用不同 snapshot。\n"
            f"manifest={expected_model_fingerprint}\n"
            f"query model={actual_fingerprint}"
        )

    kwargs = {"local_files_only": True}
    if device:
        kwargs["device"] = device

    model = SentenceTransformer(str(model_path), **kwargs)
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


def build_result_rows(
    ranking: list[tuple[float, int]],
    chunks: dict[int, dict],
    works: dict[str, dict],
) -> list[dict]:
    rows = []
    for rank, (score, row_id) in enumerate(ranking, 1):
        chunk = chunks[row_id]
        work = works[chunk["work_id"]]
        rows.append(
            {
                "rank": rank,
                "cosine": round(score, 6),
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
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Qwen Embedding shards 全库 Exact Retrieval baseline"
    )
    parser.add_argument("query", help="要检索的当前诗句或片段")
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--artifact-dir", type=Path, default=DEFAULT_ARTIFACT_DIR)
    parser.add_argument("--chunks", type=Path, default=DEFAULT_CHUNKS)
    parser.add_argument("--works", type=Path, default=DEFAULT_WORKS)
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument(
        "--device",
        help="可选：显式指定 cpu / cuda / mps；默认交给 sentence-transformers",
    )
    parser.add_argument(
        "--verify-input-hash",
        action="store_true",
        help="额外重算 Chunk JSONL SHA256；较慢，日常查询无需重复执行",
    )
    args = parser.parse_args()

    if args.top_k <= 0:
        parser.error("--top-k 必须为正整数")

    artifact_dir = args.artifact_dir.expanduser().resolve()
    chunk_path = args.chunks.expanduser().resolve()
    work_path = args.works.expanduser().resolve()
    model_path = args.model_path.expanduser().resolve()

    manifest = load_manifest(artifact_dir)

    if args.verify_input_hash:
        if not chunk_path.is_file():
            raise SystemExit(f"Chunk JSONL 不存在：{chunk_path}")
        actual_hash = sha256_file(chunk_path)
        if actual_hash != manifest.get("input_sha256"):
            raise SystemExit(
                "Chunk JSONL SHA256 与 Embedding manifest 不一致；"
                "不能把这些向量映射到当前 Chunk 文件。\n"
                f"manifest={manifest.get('input_sha256')}\n"
                f"actual={actual_hash}"
            )

    query_vector, device = encode_query(
        query=args.query,
        model_path=model_path,
        dimension=manifest["embedding_dimension"],
        expected_model_fingerprint=manifest["model_fingerprint"],
        device=args.device,
    )
    ranking = exact_search(
        artifact_dir=artifact_dir,
        manifest=manifest,
        query_vector=query_vector,
        top_k=args.top_k,
    )

    chunks = read_selected_chunks(
        chunk_path,
        [row_id for _, row_id in ranking],
    )
    works = read_selected_works(
        work_path,
        [chunks[row_id]["work_id"] for _, row_id in ranking],
    )

    result = {
        "query": args.query,
        "model": manifest["model"],
        "device": device,
        "dimension": manifest["embedding_dimension"],
        "corpus_chunks": manifest["completed_chunks"],
        "top_k": args.top_k,
        "ranking": build_result_rows(ranking, chunks, works),
        "note": (
            "Exact Retrieval 只负责候选召回；相似度不是文学关系判定。"
        ),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
