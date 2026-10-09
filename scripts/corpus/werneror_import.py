"""Normalize Werneror/Poetry CSV files into a traceable Work JSONL corpus.

This is an experiment-stage importer only:
- reads the upstream dynasty CSV files;
- preserves the four upstream fields without literary normalization;
- adds stable local provenance based on source file + record position;
- writes JSONL plus a local summary report.

It does NOT write PostgreSQL, create chunks, compute embeddings, or build indexes.

Run from the Poeticus repository root with Werneror/Poetry cloned next to it:

    python -m scripts.corpus.werneror_import

Override paths when needed:

    python -m scripts.corpus.werneror_import \
        --source-dir ../Poetry \
        --output ../poeticus-data/retrieval/corpus/werneror_works.jsonl
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from collections import Counter
from pathlib import Path

from backend.data_paths import REPOSITORY_ROOT, RETRIEVAL_CORPUS_ROOT, RETRIEVAL_REPORTS_ROOT
from typing import Iterator

SOURCE_NAME = "werneror_poetry"
EXPECTED_HEADERS = ("题目", "朝代", "作者", "内容")
DEFAULT_SOURCE_DIR = REPOSITORY_ROOT.parent / "Poetry"
DEFAULT_OUTPUT = RETRIEVAL_CORPUS_ROOT / "werneror_works.jsonl"
DEFAULT_REPORT = RETRIEVAL_REPORTS_ROOT / "werneror_corpus_import.json"
DEFAULT_EXPECTED_COUNT = 853_385
EXCLUDED_CSV = frozenset({"poetry.csv"})


def source_files(source_dir: Path) -> list[Path]:
    if not source_dir.is_dir():
        raise ValueError(f"Werneror/Poetry 目录不存在：{source_dir}")
    files = sorted(
        path
        for path in source_dir.glob("*.csv")
        if path.name not in EXCLUDED_CSV
    )
    if not files:
        raise ValueError(f"没有找到可导入的朝代 CSV：{source_dir}")
    return files


def _row_digest(row: dict[str, str]) -> bytes:
    payload = "\0".join(row[field] for field in EXPECTED_HEADERS)
    return hashlib.sha256(payload.encode("utf-8")).digest()


def iter_works(path: Path) -> Iterator[tuple[dict[str, str], bytes]]:
    """Yield normalized Work records and exact-record digests from one CSV.

    source_record_id uses the logical data-record position, starting at 1 after
    the header. It intentionally does not use physical line numbers because a
    valid CSV field may contain embedded newlines.
    """
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        headers = tuple(reader.fieldnames or ())
        if headers != EXPECTED_HEADERS:
            raise ValueError(
                f"{path.name}: CSV 表头应为 {EXPECTED_HEADERS}，实际为 {headers}"
            )

        for source_row, row in enumerate(reader, 1):
            if None in row:
                raise ValueError(f"{path.name}:{source_row}: CSV 列数异常")
            if any(row.get(field) is None for field in EXPECTED_HEADERS):
                raise ValueError(f"{path.name}:{source_row}: CSV 缺少字段")

            upstream = {field: row[field] for field in EXPECTED_HEADERS}
            source_record_id = f"{path.name}:{source_row}"
            work = {
                "work_id": f"{SOURCE_NAME}:{source_record_id}",
                "title": upstream["题目"],
                "dynasty": upstream["朝代"],
                "author": upstream["作者"],
                "content": upstream["内容"],
                "source": SOURCE_NAME,
                "source_record_id": source_record_id,
            }
            yield work, _row_digest(upstream)


def build_corpus(
    source_dir: Path,
    output_path: Path,
    report_path: Path,
    expected_count: int | None = DEFAULT_EXPECTED_COUNT,
) -> dict[str, object]:
    files = source_files(source_dir)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    tmp_output = output_path.with_name(output_path.name + ".tmp")
    if tmp_output.exists():
        tmp_output.unlink()

    total = 0
    by_file: dict[str, int] = {}
    empty_fields: Counter[str] = Counter()
    question_mark_records = 0
    duplicate_exact_records = 0
    seen_exact: set[bytes] = set()
    output_digest = hashlib.sha256()

    try:
        with tmp_output.open("w", encoding="utf-8", newline="\n") as output:
            for path in files:
                file_count = 0
                for work, exact_digest in iter_works(path):
                    total += 1
                    file_count += 1

                    for field in ("title", "dynasty", "author", "content"):
                        if not work[field]:
                            empty_fields[field] += 1
                    if "?" in work["content"]:
                        question_mark_records += 1

                    if exact_digest in seen_exact:
                        duplicate_exact_records += 1
                    else:
                        seen_exact.add(exact_digest)

                    line = json.dumps(work, ensure_ascii=False, separators=(",", ":"))
                    encoded = (line + "\n").encode("utf-8")
                    output.write(line + "\n")
                    output_digest.update(encoded)

                by_file[path.name] = file_count

        if expected_count is not None and total != expected_count:
            raise ValueError(
                f"作品总数 {total} 与预期 {expected_count} 不一致；"
                "保留上游仓库不动，先检查输入版本或文件范围"
            )

        os.replace(tmp_output, output_path)
    except Exception:
        tmp_output.unlink(missing_ok=True)
        raise

    report: dict[str, object] = {
        "source": SOURCE_NAME,
        "source_dir": str(source_dir),
        "output": str(output_path),
        "files": len(files),
        "records": total,
        "by_file": by_file,
        "empty_fields": dict(empty_fields),
        "question_mark_records": question_mark_records,
        "duplicate_exact_records": duplicate_exact_records,
        "jsonl_sha256": output_digest.hexdigest(),
        "excluded_csv": sorted(
            path.name for path in source_dir.glob("*.csv")
            if path.name in EXCLUDED_CSV
        ),
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Werneror/Poetry CSV → 可追溯 Work JSONL（不写数据库、不做 Embedding）"
    )
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--expect-count",
        type=int,
        default=DEFAULT_EXPECTED_COUNT,
        help="预期作品总数；传 0 可关闭总数校验",
    )
    args = parser.parse_args()
    if args.expect_count < 0:
        parser.error("--expect-count 不能为负数")

    report = build_corpus(
        source_dir=args.source_dir,
        output_path=args.output,
        report_path=args.report,
        expected_count=args.expect_count or None,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
