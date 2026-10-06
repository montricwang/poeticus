"""Create sentence-level Retrieval chunks from normalized Werneror Works.

This stage is intentionally still pre-Embedding:

    Work JSONL -> sentence Chunk JSONL

Each chunk keeps a parent work_id plus half-open [start, end) character
offsets into the original Work.content, so any retrieved text can be traced
back without duplicating title/author/dynasty metadata on every chunk.

Default sentence policy cuts after 。！？!? and absorbs adjacent sentence-end
marks plus common closing quotation/bracket marks. Semicolons remain inside a
sentence for this baseline.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Iterator

DEFAULT_INPUT = Path("data/output/retrieval/werneror_works.jsonl")
DEFAULT_OUTPUT = Path("data/output/retrieval/werneror_chunks_sentence.jsonl")
DEFAULT_REPORT = Path("data/reports/werneror_sentence_chunks.json")
DEFAULT_EXPECTED_WORKS = 853_385
DEFAULT_EXPECTED_CHUNKS = 4_822_082

POLICY = "sentence"
SENTENCE_END = frozenset("。！？!?")
CLOSING_MARKS = frozenset("”’」』】）》")


def _trim_span(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def _has_semantic_text(text: str) -> bool:
    return any(
        not ch.isspace() and ch not in SENTENCE_END and ch not in CLOSING_MARKS
        for ch in text
    )


def split_sentence_spans(text: str) -> Iterator[tuple[int, int, str]]:
    """Yield exact sentence spans as (start, end, text).

    Offsets are Python Unicode code-point offsets into the original content.
    """
    start = 0
    index = 0
    size = len(text)

    while index < size:
        if text[index] not in SENTENCE_END:
            index += 1
            continue

        index += 1
        while index < size and text[index] in SENTENCE_END:
            index += 1
        while index < size and text[index] in CLOSING_MARKS:
            index += 1

        left, right = _trim_span(text, start, index)
        candidate = text[left:right]
        if candidate and _has_semantic_text(candidate):
            yield left, right, candidate
        start = index

    left, right = _trim_span(text, start, size)
    candidate = text[left:right]
    if candidate and _has_semantic_text(candidate):
        yield left, right, candidate


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


def build_sentence_chunks(
    input_path: Path,
    output_path: Path,
    report_path: Path,
    expected_works: int | None = DEFAULT_EXPECTED_WORKS,
    expected_chunks: int | None = DEFAULT_EXPECTED_CHUNKS,
) -> dict:
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
                    split_sentence_spans(work["content"])
                ):
                    if work["content"][start:end] != text:
                        raise AssertionError(
                            f"{work['source_record_id']}: Chunk offset 无法还原原文"
                        )
                    record = {
                        "chunk_id": (
                            f"{work['work_id']}:{POLICY}:{chunk_index}"
                        ),
                        "work_id": work["work_id"],
                        "policy": POLICY,
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

    report = {
        "policy": POLICY,
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
