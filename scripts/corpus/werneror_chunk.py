"""把 Werneror Work 转换为句子级 Retrieval Chunk。

此阶段发生在 Embedding 之前：

    Work JSONL → sentence Chunk JSONL

每个 Chunk 保留父级 work_id，以及指向 Work.content 的左闭右开
字符区间 [start, end)，用于回溯原文，而不在每个 Chunk 里重复保存
题名、作者和朝代等元数据。

默认句子切分在 。！？!? 之后，并合并相邻句末标点与常见右引号、
右括号；当前基线不按分号断句。"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import TypedDict

from backend.data_paths import RETRIEVAL_CORPUS_ROOT, RETRIEVAL_REPORTS_ROOT
from backend.retrieval.text_units import (
    split_clause_spans,
    split_sentence_spans,
)
DEFAULT_INPUT = RETRIEVAL_CORPUS_ROOT / "werneror_works.jsonl"
DEFAULT_OUTPUT = RETRIEVAL_CORPUS_ROOT / "werneror_chunks_sentence.jsonl"
DEFAULT_REPORT = RETRIEVAL_REPORTS_ROOT / "werneror_sentence_chunks.json"
DEFAULT_EXPECTED_WORKS = 853_385
DEFAULT_EXPECTED_CHUNKS = 0

POLICY = "sentence"
CLAUSE_POLICY = "clause"


class ChunkCounts(TypedDict):
    policy: str
    input: str
    output: str
    works: int
    chunks: int
    chunks_per_work: float
    works_without_chunks: int
    max_chunk_chars: int
    chunks_over_chars: dict[str, int]
    offset_semantics: str


def _iter_works(path: Path):
    with path.open(encoding="utf-8") as stream:
        for line_no, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                work = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Work JSONL 第 {line_no} 行无法解析") from exc
            required = {"work_id", "content", "source_record_id"}
            if not isinstance(work, dict) or not required <= set(work):
                raise ValueError(f"Work JSONL 第 {line_no} 行缺少必要字段")
            if not isinstance(work["content"], str) or not work["content"]:
                raise ValueError(
                    f"{work.get('source_record_id', line_no)}: content 不是非空字符串"
                )
            yield work


def _build_chunks(
    input_path: Path,
    output_path: Path,
    report_path: Path,
    *,
    policy: str,
    splitter,
    expected_works: int | None = DEFAULT_EXPECTED_WORKS,
    expected_chunks: int | None = DEFAULT_EXPECTED_CHUNKS,
) -> ChunkCounts:
    if not input_path.is_file():
        raise ValueError(f"Work JSONL 不存在：{input_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_output = output_path.with_name(output_path.name + ".tmp")
    tmp_output.unlink(missing_ok=True)

    works = 0
    chunks = 0
    works_without_chunks = 0
    max_chunk_chars = 0
    over_128 = 0
    over_256 = 0
    over_512 = 0

    try:
        with tmp_output.open("w", encoding="utf-8", newline="\n") as output:
            for work in _iter_works(input_path):
                works += 1
                work_chunk_count = 0

                for chunk_index, (start, end, text) in enumerate(
                    splitter(work["content"])
                ):
                    if work["content"][start:end] != text:
                        raise AssertionError(
                            f"{work['source_record_id']}: Chunk offset 无法还原原文"
                        )
                    record = {
                        "chunk_id": f"{work['work_id']}:{policy}:{chunk_index}",
                        "work_id": work["work_id"],
                        "policy": policy,
                        "chunk_index": chunk_index,
                        "start": start,
                        "end": end,
                        "text": text,
                    }
                    output.write(
                        json.dumps(
                            record, ensure_ascii=False, separators=(",", ":")
                        )
                        + "\n"
                    )
                    chunks += 1
                    work_chunk_count += 1

                    length = len(text)
                    max_chunk_chars = max(max_chunk_chars, length)
                    over_128 += length > 128
                    over_256 += length > 256
                    over_512 += length > 512

                if work_chunk_count == 0:
                    works_without_chunks += 1

        if expected_works is not None and works != expected_works:
            raise ValueError(
                f"读取作品 {works} 首，与预期 {expected_works} 不一致"
            )
        if expected_chunks is not None and chunks != expected_chunks:
            raise ValueError(
                f"生成 Chunk {chunks} 条，与画像预期 {expected_chunks} 不一致；"
                "请先检查切分规则与画像口径"
            )
        if works_without_chunks:
            raise ValueError(
                f"有 {works_without_chunks} 首作品没有产生任何 Chunk；请先检查"
            )

        os.replace(tmp_output, output_path)
    except Exception:
        tmp_output.unlink(missing_ok=True)
        raise

    report: ChunkCounts = {
        "policy": policy,
        "input": str(input_path),
        "output": str(output_path),
        "works": works,
        "chunks": chunks,
        "chunks_per_work": round(chunks / works, 3) if works else 0,
        "works_without_chunks": works_without_chunks,
        "max_chunk_chars": max_chunk_chars,
        "chunks_over_chars": {
            "128": over_128,
            "256": over_256,
            "512": over_512,
        },
        "offset_semantics": "[start, end) Unicode code-point offsets into Work.content",
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def build_sentence_chunks(
    input_path: Path,
    output_path: Path,
    report_path: Path,
    expected_works: int | None = DEFAULT_EXPECTED_WORKS,
    expected_chunks: int | None = DEFAULT_EXPECTED_CHUNKS,
) -> ChunkCounts:
    return _build_chunks(
        input_path,
        output_path,
        report_path,
        policy=POLICY,
        splitter=split_sentence_spans,
        expected_works=expected_works,
        expected_chunks=expected_chunks,
    )


def build_clause_chunks(
    input_path: Path,
    output_path: Path,
    report_path: Path,
    expected_works: int | None = DEFAULT_EXPECTED_WORKS,
    expected_chunks: int | None = DEFAULT_EXPECTED_CHUNKS,
) -> ChunkCounts:
    return _build_chunks(
        input_path,
        output_path,
        report_path,
        policy=CLAUSE_POLICY,
        splitter=split_clause_spans,
        expected_works=expected_works,
        expected_chunks=expected_chunks,
    )

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Werneror Work JSONL -> sentence Chunk JSONL"
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--expect-works", type=int, default=DEFAULT_EXPECTED_WORKS
    )
    parser.add_argument(
        "--expect-chunks", type=int, default=DEFAULT_EXPECTED_CHUNKS
    )
    args = parser.parse_args()
    if args.expect_works < 0 or args.expect_chunks < 0:
        parser.error("预期数量不能为负数；传 0 可关闭对应校验")

    report = build_sentence_chunks(
        args.input,
        args.output,
        args.report,
        expected_works=args.expect_works or None,
        expected_chunks=args.expect_chunks or None,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
