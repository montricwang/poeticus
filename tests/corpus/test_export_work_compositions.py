"""Work 拼接关系导出的契约：准确位置、可查询、可追溯、只读源。"""
from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

import pytest

from scripts.corpus.export_work_compositions import export


def _fixture(tmp_path: Path, *, broken: bool = False) -> tuple[Path, Path]:
    a = "懒向青门学种瓜。只将渔钓送年华。双双新燕飞春岸，片片轻鸥落晚沙。"
    b = "歌缥渺，橹呕哑。酒如清露鲊如花。逢人问道归何处，笑指船儿此是家。"
    items = [
        ("宋.csv:1", a, "陆游"),
        ("宋.csv:2", b, "陆游"),
        ("宋.csv:3", a + ("误" if broken else "") + b, "陆游"),
        ("宋.csv:4", a + a, "陆游"),
        ("宋.csv:5", a, "杜甫"),
    ]
    corpus = tmp_path / "works.jsonl"
    corpus.write_text(
        "".join(
            json.dumps({
                "work_id": f"werneror_poetry:{source}", "source_record_id": source,
                "content": text, "author": author, "dynasty": "宋",
            }, ensure_ascii=False) + "\n"
            for source, text, author in items
        ),
        encoding="utf-8",
    )
    audit = tmp_path / "audit.jsonl"
    audit.write_text(
        "".join(
            json.dumps({
                "work_id": f"werneror_poetry:{parent}",
                "source_record_id": parent,
                "member_source_record_ids": members,
            }, ensure_ascii=False) + "\n"
            for parent, members in [
                ("宋.csv:3", ["宋.csv:1", "宋.csv:2"]),
                ("宋.csv:4", ["宋.csv:1", "宋.csv:1"]),
            ]
        ),
        encoding="utf-8",
    )
    return corpus, audit


def test_export_creates_queryable_relation_table_and_postgres_csv(tmp_path: Path):
    corpus, audit = _fixture(tmp_path)
    source_before = corpus.read_bytes()
    report = export(
        works_path=corpus, audit_path=audit, output_dir=tmp_path / "output",
    )
    assert report["parent_works"] == 2
    assert report["relation_rows"] == 4
    assert report["distinct_member_works"] == 2
    assert report["relation_kind"] == "exact_concatenation"
    assert corpus.read_bytes() == source_before

    db = sqlite3.connect(tmp_path / "output/work_compositions.sqlite3")
    try:
        group = "werneror_poetry:宋.csv:3"
        first = "werneror_poetry:宋.csv:1"
        rows = db.execute(
            "SELECT member_work_id, member_order, start_char, end_char "
            "FROM work_compositions WHERE parent_work_id = ? ORDER BY member_order",
            (group,),
        ).fetchall()
        assert [(r[0], r[1]) for r in rows] == [
            ("werneror_poetry:宋.csv:1", 1),
            ("werneror_poetry:宋.csv:2", 2),
        ]
        assert rows[0][2] == 0
        assert rows[0][3] == rows[1][2]
        assert db.execute(
            "SELECT DISTINCT parent_work_id FROM work_compositions "
            "WHERE member_work_id = ? ORDER BY parent_work_id", (first,),
        ).fetchall() == [
            ("werneror_poetry:宋.csv:3",),
            ("werneror_poetry:宋.csv:4",),
        ]
        # 某独立诗篇重复出现时，不能以 (parent, member) 为联合主键。
        assert db.execute(
            "SELECT COUNT(*) FROM work_compositions WHERE parent_work_id = ?",
            ("werneror_poetry:宋.csv:4",),
        ).fetchone()[0] == 2
    finally:
        db.close()

    with (tmp_path / "output/work_compositions.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 4
    assert rows[0]["match_kind"] == "exact_concatenation"
    assert rows[0]["member_order"] == "1"
    assert (tmp_path / "output/work_compositions_manifest.json").exists()


def test_refuses_incorrect_concat_and_does_not_modify_input(tmp_path: Path):
    corpus, audit = _fixture(tmp_path, broken=True)
    with pytest.raises(ValueError, match="逐字匹配"):
        export(works_path=corpus, audit_path=audit, output_dir=tmp_path / "output")


def test_no_implicit_overwrite_of_existing_relation_snapshot(tmp_path: Path):
    corpus, audit = _fixture(tmp_path)
    output_dir = tmp_path / "output"
    export(works_path=corpus, audit_path=audit, output_dir=output_dir)
    with pytest.raises(FileExistsError, match="已存在关系快照"):
        export(works_path=corpus, audit_path=audit, output_dir=output_dir)


def test_unknown_work_and_duplicate_host_are_rejected(tmp_path: Path):
    corpus, audit = _fixture(tmp_path)
    text = audit.read_text(encoding="utf-8")
    audit.write_text(text + text.splitlines(keepends=True)[0], encoding="utf-8")
    with pytest.raises(ValueError, match="重复出现"):
        export(works_path=corpus, audit_path=audit, output_dir=tmp_path / "output")

    audit.write_text(text.replace("宋.csv:2", "宋.csv:missing"), encoding="utf-8")
    with pytest.raises(ValueError, match="缺少审计中的 Work ID"):
        export(works_path=corpus, audit_path=audit, output_dir=tmp_path / "output")
