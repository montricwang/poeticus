"""将已审计的 Werneror 精确拼接关系导出为可查询的 SQLite 和 PostgreSQL CSV。

不修改原始 Corpus、既有检索索引或线上 PostgreSQL。输入必须是本地 Corpus
和 werneror_group_audit 产生的明细；导出时重新逐字验证每条关系。

运行：
  python -m scripts.corpus.export_work_compositions

输出位于私人 poeticus-data/retrieval/relationships/，不会提交到 Git。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path

from backend.data_paths import RETRIEVAL_CORPUS_ROOT, RETRIEVAL_REPORTS_ROOT, RETRIEVAL_ROOT

DEFAULT_WORKS = RETRIEVAL_CORPUS_ROOT / "werneror_works.jsonl"
DEFAULT_AUDIT = RETRIEVAL_REPORTS_ROOT / "werneror_group_audit_matches.jsonl"
DEFAULT_OUTPUT_DIR = RETRIEVAL_ROOT / "relationships"

CSV_COLUMNS = (
    "parent_work_id",
    "member_work_id",
    "member_order",
    "start_char",
    "end_char",
    "match_kind",
)
CREATE_TABLE = """
CREATE TABLE work_compositions (
    parent_work_id TEXT NOT NULL,
    member_work_id TEXT NOT NULL,
    member_order INTEGER NOT NULL CHECK (member_order >= 1),
    start_char INTEGER NOT NULL CHECK (start_char >= 0),
    end_char INTEGER NOT NULL CHECK (end_char > start_char),
    match_kind TEXT NOT NULL CHECK (match_kind = 'exact_concatenation'),
    PRIMARY KEY (parent_work_id, member_order),
    CHECK (parent_work_id <> member_work_id)
);
CREATE INDEX idx_work_compositions_member
    ON work_compositions (member_work_id);
"""


def _audit_rows(path: Path) -> Iterator[dict[str, object]]:
    with path.open(encoding="utf-8") as stream:
        for line_no, line in enumerate(stream, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"audit 第 {line_no} 行不是对象")
            yield row


def _source_to_work_id(source_id: str) -> str:
    # 与 werneror_import.py 生成的 Work ID 契约一致。
    return f"werneror_poetry:{source_id}"


def _wanted_work_ids(audit_path: Path) -> tuple[set[str], int]:
    wanted: set[str] = set()
    parents: set[str] = set()
    for item in _audit_rows(audit_path):
        parent = item["work_id"]
        source_ids = item["member_source_record_ids"]
        if not isinstance(parent, str) or not isinstance(source_ids, list) or len(source_ids) < 2:
            raise ValueError("audit 缺少合集 Work ID 或至少两个成员")
        if parent in parents:
            raise ValueError(f"合集在审计中重复出现：{parent}")
        parents.add(parent)
        wanted.add(parent)
        for source_id in source_ids:
            if not isinstance(source_id, str):
                raise ValueError(f"合集 {parent} 的成员来源 ID 无效")
            wanted.add(_source_to_work_id(source_id))
    return wanted, len(parents)


def _load_selected_works(path: Path, wanted: set[str]) -> dict[str, dict[str, str]]:
    works: dict[str, dict[str, str]] = {}
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            record = json.loads(line)
            work_id = record["work_id"]
            if work_id not in wanted:
                continue
            if work_id in works:
                raise ValueError(f"Corpus 中 Work ID 重复：{work_id}")
            works[work_id] = {
                "content": record["content"],
                "author": record["author"],
                "dynasty": record["dynasty"],
                "source_record_id": record["source_record_id"],
            }
    missing = wanted - works.keys()
    if missing:
        raise ValueError(f"Corpus 缺少审计中的 Work ID：{sorted(missing)[:5]}")
    return works


def _validated_members(
    item: dict[str, object],
    works: dict[str, dict[str, str]],
    *,
    min_member_chars: int,
) -> Iterator[tuple[str, str, int, int, int, str]]:
    parent_id = item["work_id"]
    source_ids = item["member_source_record_ids"]
    if not isinstance(parent_id, str) or not isinstance(source_ids, list):
        raise ValueError("审计中的 Work ID 无效")
    parent = works[parent_id]
    if parent["source_record_id"] != item["source_record_id"]:
        raise ValueError(f"合集来源 ID 不一致：{parent_id}")
    offset = 0
    for order, source_id in enumerate(source_ids, 1):
        if not isinstance(source_id, str):
            raise ValueError(f"成员来源 ID 无效：{parent_id}")
        member_id = _source_to_work_id(source_id)
        member = works[member_id]
        text = member["content"]
        if (
            member_id == parent_id
            or len(text) < min_member_chars
            or len(text) >= len(parent["content"])
            or member["author"] != parent["author"]
            or member["dynasty"] != parent["dynasty"]
            or member["source_record_id"] != source_id
            or not parent["content"].startswith(text, offset)
        ):
            raise ValueError(f"成员不能在此位置逐字匹配：{parent_id} / {member_id} / {offset}")
        end = offset + len(text)
        yield parent_id, member_id, order, offset, end, "exact_concatenation"
        offset = end
    if offset != len(parent["content"]):
        raise ValueError(f"成员拼接后未覆盖合集全文：{parent_id}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(2 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def export(
    *,
    works_path: Path,
    audit_path: Path,
    output_dir: Path,
    min_member_chars: int = 24,
) -> dict[str, object]:
    """从两份只读材料生成附带来源指纹的 SQLite 和 PostgreSQL CSV 快照。"""
    wanted, expected_parents = _wanted_work_ids(audit_path)
    works = _load_selected_works(works_path, wanted)
    output_dir.mkdir(parents=True, exist_ok=True)
    db_path = output_dir / "work_compositions.sqlite3"
    csv_path = output_dir / "work_compositions.csv"
    manifest_path = output_dir / "work_compositions_manifest.json"
    # 不覆盖已有版本：避免无意识更换运行中的映射。
    for path in (db_path, csv_path, manifest_path):
        if path.exists():
            raise FileExistsError(f"已存在关系快照，请先选择新的输出目录：{path}")

    count = 0
    parents = 0
    used_members: set[str] = set()
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(CREATE_TABLE)
        with csv_path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(CSV_COLUMNS)
            with conn:
                for item in _audit_rows(audit_path):
                    relations = list(
                        _validated_members(item, works, min_member_chars=min_member_chars)
                    )
                    if len(relations) < 2:
                        raise ValueError("合法合集至少要有两个成员")
                    conn.executemany(
                        "INSERT INTO work_compositions VALUES (?, ?, ?, ?, ?, ?)",
                        relations,
                    )
                    writer.writerows(relations)
                    count += len(relations)
                    parents += 1
                    used_members.update(row[1] for row in relations)

        db_count = conn.execute("SELECT COUNT(*) FROM work_compositions").fetchone()[0]
        if count != db_count or parents != expected_parents:
            raise ValueError("写出行数与审计记录数不符")

        manifest: dict[str, object] = {
            "relation_kind": "exact_concatenation",
            "corpus_sha256": _sha256(works_path),
            "audit_sha256": _sha256(audit_path),
            "csv_sha256": _sha256(csv_path),
            "min_member_chars": min_member_chars,
            "parent_works": parents,
            "relation_rows": count,
            "distinct_member_works": len(used_members),
            "csv_path": str(csv_path),
            "sqlite_path": str(db_path),
            "notes": [
                "成员位置采用 Python Unicode 字符索引，起点含、终点不含。",
                "匹配的是精确正文拼接，不代表已校勘文学组诗关系。",
                "同一独立 Work 可以在合集的不同位置重复出现。",
                "只供 Poem Retrieval 的业务候选校验；不与阅读库 poems UUID 关联。",
            ],
        }
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return manifest
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--works", type=Path, default=DEFAULT_WORKS)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--min-member-chars", type=int, default=24)
    args = parser.parse_args()
    if args.min_member_chars < 24:
        parser.error("最小成员长度不能小于 24，避免和现有审计契约脱节")
    report = export(
        works_path=args.works,
        audit_path=args.audit,
        output_dir=args.output_dir,
        min_member_chars=args.min_member_chars,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
