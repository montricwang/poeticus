"""将 Werneror/Poetry 的 CSV 规范化为可追踪来源的 Work JSONL。

这是实验阶段的语料导入工具：
- 读取上游按朝代划分的 CSV；
- 原样保留上游四个字段，不进行文学文本规范化；
- 根据来源文件和记录位置增加稳定的本地来源标识；
- 输出 JSONL 及本地摘要报告。

本脚本不写 PostgreSQL、不切分 Chunk、不计算 Embedding、不构建索引。

将 Werneror/Poetry 放在 Poeticus 同级目录后，于仓库根目录运行：

    python -m scripts.corpus.werneror_import

必要时可以覆盖路径：

    python -m scripts.corpus.werneror_import \
        --source-dir ../Poetry \
        --output ../poeticus-data/retrieval/corpus/werneror_works.jsonl"""
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
    """依次返回单份 CSV 的规范化 Work 记录及每条记录的摘要指纹。

    source_record_id 使用跳过表头后从 1 开始的逻辑数据记录序号，
    不使用物理行号，因为合法的 CSV 字段可能包含换行。
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
