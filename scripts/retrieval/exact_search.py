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
DEFAULT_MODEL_ROOT = Path("../poeticus-data/models")
DEFAULT_CHUNKS = DEFAULT_DATA_ROOT / "werneror_chunks_sentence.jsonl"
DEFAULT_WORKS = DEFAULT_DATA_ROOT / "werneror_works.jsonl"
DEFAULT_ARTIFACT_DIR = (
    DEFAULT_DATA_ROOT / "embeddings/qwen3_0.6b_sentence_1024"
)
DEFAULT_TOP_K = 20

# Coarse chronology for the current Werneror labels.
# Fully earlier periods are admitted. Transitional labels that begin before
# the target dynasty and overlap its start (for example 唐末宋初 -> 宋) are
# also admitted for recall, leaving exact author/work chronology to a later layer.
# Same-dynasty and parallel regimes remain excluded in this baseline.
DYNASTY_PERIODS = {
    "先秦": (-3000, -221),
    "秦": (-221, -206),
    "汉": (-206, 220),
    "魏晋": (220, 420),
    "魏晋末南北朝初": (400, 440),
    "南北朝": (420, 589),
    "隋": (581, 618),
    "隋末唐初": (610, 630),
    "唐": (618, 907),
    "唐末宋初": (880, 1000),
    "辽": (916, 1125),
    "宋": (960, 1279),
    "金": (1115, 1234),
    "宋末金初": (1110, 1140),
    "宋末元初": (1250, 1300),
    "金末元初": (1210, 1300),
    "元": (1271, 1368),
    "元末明初": (1350, 1400),
    "明": (1368, 1644),
    "明末清初": (1620, 1680),
    "清": (1636, 1912),
    "清末民国初": (1890, 1930),
    "清末近现代初": (1890, 1930),
    "近现代": (1912, 1949),
    "民国末当代初": (1940, 1960),
    "近现代末当代初": (1940, 1960),
    "当代": (1949, 2100),
}


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


def resolve_model_path(manifest: dict, requested_path: Path | None) -> Path:
    if requested_path is not None:
        return requested_path.expanduser().resolve()

    fingerprint = manifest["model_fingerprint"]
    return (
        DEFAULT_MODEL_ROOT
        / f"Qwen3-Embedding-0.6B-{fingerprint[:12]}"
    ).resolve()


def ensure_model_snapshot(
    model_path: Path,
    expected_model_fingerprint: str,
) -> Path:
    from scripts.corpus.qwen_embedding_build import fingerprint_model_dir

    if not model_path.exists():
        try:
            from modelscope import snapshot_download
        except ImportError as exc:
            raise RuntimeError(
                "本地缺少与 Embedding Artifact 对应的 Qwen 模型，"
                "自动下载需要 modelscope；请安装 requirements-retrieval.txt"
            ) from exc

        model_path.parent.mkdir(parents=True, exist_ok=True)
        print(
            "本地没有与 Embedding Artifact 对应的 Qwen 模型，开始下载……",
            flush=True,
        )
        snapshot_download(MODEL_NAME, local_dir=str(model_path))

    if not model_path.is_dir():
        raise ValueError(f"本地模型路径不是目录：{model_path}")

    actual_fingerprint = fingerprint_model_dir(model_path)
    if actual_fingerprint != expected_model_fingerprint:
        raise ValueError(
            "本地 Qwen 模型与生成 Corpus Embedding 的模型不一致。\n"
            f"manifest={expected_model_fingerprint}\n"
            f"local={actual_fingerprint}\n"
            f"path={model_path}"
        )
    return model_path


def candidate_prior_dynasties(target_dynasty: str) -> set[str]:
    if target_dynasty not in DYNASTY_PERIODS:
        raise ValueError(
            f"尚未定义朝代时间范围：{target_dynasty!r}；"
            "不能安全地做前代过滤"
        )

    target_start, _ = DYNASTY_PERIODS[target_dynasty]
    allowed = set()
    for dynasty, (candidate_start, candidate_end) in DYNASTY_PERIODS.items():
        if dynasty == target_dynasty:
            continue

        fully_earlier = candidate_end < target_start
        transitional_overlap = (
            candidate_start < target_start <= candidate_end
            and "末" in dynasty
            and "初" in dynasty
        )
        if fully_earlier or transitional_overlap:
            allowed.add(dynasty)

    return allowed


def build_dynasty_row_mask(
    *,
    work_path: Path,
    chunk_path: Path,
    allowed_dynasties: set[str],
    expected_chunks: int,
):
    try:
        import numpy as np
    except ImportError as exc:
        raise RuntimeError(
            "朝代过滤需要 NumPy；请安装 requirements-retrieval.txt"
        ) from exc

    if not work_path.is_file():
        raise ValueError(f"Work JSONL 不存在：{work_path}")
    if not chunk_path.is_file():
        raise ValueError(f"Chunk JSONL 不存在：{chunk_path}")

    allowed_work_ids: set[str] = set()
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
            if work.get("dynasty") in allowed_dynasties:
                work_id = work.get("work_id")
                if not isinstance(work_id, str) or not work_id:
                    raise ValueError(
                        f"Work JSONL 第 {line_no} 行缺少有效 work_id"
                    )
                allowed_work_ids.add(work_id)

    mask = np.zeros(expected_chunks, dtype=bool)
    logical_row = 0
    with chunk_path.open(encoding="utf-8") as stream:
        for line_no, line in enumerate(stream, 1):
            if not line.strip():
                continue
            if logical_row >= expected_chunks:
                raise ValueError(
                    "Chunk JSONL 条数超过 Embedding manifest 的 completed_chunks"
                )
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Chunk JSONL 第 {line_no} 行无法解析"
                ) from exc
            if chunk.get("work_id") in allowed_work_ids:
                mask[logical_row] = True
            logical_row += 1

    if logical_row != expected_chunks:
        raise ValueError(
            f"Chunk JSONL 实际 {logical_row:,} 条，"
            f"Embedding manifest 为 {expected_chunks:,} 条"
        )
    return mask


def find_probe_rows(
    *,
    work_path: Path,
    chunk_path: Path,
    probe_text: str,
    probe_author: str | None = None,
) -> set[int]:
    if not probe_text:
        raise ValueError("probe_text 不能为空")

    matching_work_ids: set[str] = set()
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
                matching_work_ids.add(work["work_id"])

    rows: set[int] = set()
    logical_row = 0
    with chunk_path.open(encoding="utf-8") as stream:
        for line_no, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Chunk JSONL 第 {line_no} 行无法解析"
                ) from exc
            if (
                chunk.get("work_id") in matching_work_ids
                and probe_text in chunk.get("text", "")
            ):
                rows.add(logical_row)
            logical_row += 1

    return rows


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
    row_mask=None,
    probe_rows: set[int] | None = None,
) -> tuple[list[tuple[float, int]], dict[int, dict]]:
    """Scan every shard and return Top-K plus optional exact probe ranks."""
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
    probe_rows = probe_rows or set()
    probe_scores: dict[int, float] = {}
    scored_values = []
    scored_rows = []

    for shard_no, item in enumerate(manifest["completed_shards"], 1):
        expected_rows = item["end"] - item["start"]
        shard_mask = None
        if row_mask is not None:
            shard_mask = row_mask[item["start"]:item["end"]]
            if shard_mask.shape != (expected_rows,):
                raise ValueError("row_mask 与 Embedding shard 范围不一致")
            if not shard_mask.any():
                continue

        path = artifact_dir / item["file"]
        vectors = np.load(path, mmap_mode="r", allow_pickle=False)
        expected_shape = (expected_rows, dimension)
        if vectors.shape != expected_shape:
            raise ValueError(
                f"{path.name} shape={vectors.shape}，预期 {expected_shape}"
            )

        # The corpus Artifact is float16 for storage. Exact baseline converts
        # one 10k shard at a time to float32 before the dot product, keeping
        # peak memory bounded while avoiding float16 accumulation as the
        # reference score.
        matrix = np.asarray(vectors, dtype=np.float32)

        if shard_mask is None:
            eligible_local = np.arange(matrix.shape[0])
        else:
            eligible_local = np.flatnonzero(shard_mask)

        scores = matrix[eligible_local] @ query
        global_rows = item["start"] + eligible_local

        if probe_rows:
            scored_values.append(scores.copy())
            scored_rows.append(global_rows.copy())
            for local_index, global_row in enumerate(global_rows):
                row_id = int(global_row)
                if row_id in probe_rows:
                    probe_scores[row_id] = float(scores[local_index])

        local_k = min(top_k, scores.shape[0])
        if local_k == scores.shape[0]:
            selected = np.arange(scores.shape[0])
        else:
            selected = np.argpartition(scores, -local_k)[-local_k:]

        candidates = [
            (
                float(scores[index]),
                item["start"] + int(eligible_local[index]),
            )
            for index in selected
        ]
        best = merge_top_k(best, candidates, top_k)

        print(
            f"Exact search: {shard_no}/{len(manifest['completed_shards'])}",
            end="\r",
            flush=True,
        )

    print(" " * 80, end="\r", flush=True)

    probes: dict[int, dict] = {}
    if probe_rows:
        missing = sorted(probe_rows - set(probe_scores))
        if missing:
            raise ValueError(
                "Probe Chunk 不在当前可检索范围内："
                + ", ".join(str(row) for row in missing[:10])
            )

        all_scores = np.concatenate(scored_values)
        all_rows = np.concatenate(scored_rows)
        for row_id, score in probe_scores.items():
            rank = 1 + int(np.count_nonzero(all_scores > score))
            rank += int(
                np.count_nonzero(
                    (all_scores == score) & (all_rows < row_id)
                )
            )
            probes[row_id] = {
                "cosine": round(score, 6),
                "rank": rank,
            }

    return best, probes


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

    ensure_model_snapshot(model_path, expected_model_fingerprint)

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
    parser.add_argument(
        "--model-path",
        type=Path,
        help=(
            "可选：指定本地模型目录；默认按 Embedding manifest 的模型 "
            "fingerprint 使用 poeticus-data/models 下的独立目录，缺失时自动下载"
        ),
    )
    parser.add_argument("--artifact-dir", type=Path, default=DEFAULT_ARTIFACT_DIR)
    parser.add_argument("--chunks", type=Path, default=DEFAULT_CHUNKS)
    parser.add_argument("--works", type=Path, default=DEFAULT_WORKS)
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument(
        "--before-dynasty",
        help=(
            "只让前代候选参与排名；明确更早的朝代和跨入目标朝代初期的"
            "过渡标签会保留，同朝代和并行政权暂不纳入"
        ),
    )
    parser.add_argument(
        "--probe-text",
        help="诊断：指定已知目标文本，报告它在全部候选中的精确分数与名次",
    )
    parser.add_argument(
        "--probe-author",
        help="诊断：与 --probe-text 一起使用，用作者名缩小目标范围",
    )
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
    if args.probe_author and not args.probe_text:
        parser.error("--probe-author 必须和 --probe-text 一起使用")

    artifact_dir = args.artifact_dir.expanduser().resolve()
    chunk_path = args.chunks.expanduser().resolve()
    work_path = args.works.expanduser().resolve()

    manifest = load_manifest(artifact_dir)
    model_path = resolve_model_path(manifest, args.model_path)

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

    chronology = None
    row_mask = None
    if args.before_dynasty:
        allowed_dynasties = candidate_prior_dynasties(args.before_dynasty)
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
            "before_dynasty": args.before_dynasty,
            "allowed_dynasties": sorted(allowed_dynasties),
            "eligible_chunks": int(row_mask.sum()),
            "eligible_shards": eligible_shards,
            "total_shards": len(manifest["completed_shards"]),
        }
        if chronology["eligible_chunks"] == 0:
            raise SystemExit("朝代过滤后没有可检索的 Chunk")

    probe_rows: set[int] = set()
    if args.probe_text:
        probe_rows = find_probe_rows(
            work_path=work_path,
            chunk_path=chunk_path,
            probe_text=args.probe_text,
            probe_author=args.probe_author,
        )
        if not probe_rows:
            raise SystemExit(
                "没有找到符合 probe 条件的 Chunk："
                f"text={args.probe_text!r}, author={args.probe_author!r}"
            )

    query_vector, device = encode_query(
        query=args.query,
        model_path=model_path,
        dimension=manifest["embedding_dimension"],
        expected_model_fingerprint=manifest["model_fingerprint"],
        device=args.device,
    )
    ranking, probe_stats = exact_search(
        artifact_dir=artifact_dir,
        manifest=manifest,
        query_vector=query_vector,
        top_k=args.top_k,
        row_mask=row_mask,
        probe_rows=probe_rows,
    )

    selected_rows = {
        row_id for _, row_id in ranking
    } | set(probe_stats)
    chunks = read_selected_chunks(
        chunk_path,
        selected_rows,
    )
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

    result = {
        "query": args.query,
        "model": manifest["model"],
        "device": device,
        "dimension": manifest["embedding_dimension"],
        "corpus_chunks": manifest["completed_chunks"],
        "top_k": args.top_k,
        "chronology_filter": chronology,
        "ranking": build_result_rows(ranking, chunks, works),
        "probes": probe_results,
        "note": (
            "Exact Retrieval 只负责候选召回；相似度不是文学关系判定。"
        ),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
