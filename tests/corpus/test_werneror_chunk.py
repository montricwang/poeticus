import json

import pytest

from scripts.corpus.werneror_chunk import (
    build_clause_chunks,
    build_sentence_chunks,
    split_clause_spans,
    split_sentence_spans,
)


def _work(record_id, content):
    return {
        "work_id": f"werneror_poetry:{record_id}",
        "title": "题",
        "dynasty": "唐",
        "author": "作者",
        "content": content,
        "source": "werneror_poetry",
        "source_record_id": record_id,
    }


def _write_jsonl(path, records):
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records),
        encoding="utf-8",
    )


def test_split_sentence_spans_preserves_punctuation_quotes_and_offsets():
    text = "  “第一句？！”\n第二句；还没结束。  尾巴  "
    chunks = list(split_sentence_spans(text))

    assert [chunk[2] for chunk in chunks] == [
        "“第一句？！”",
        "第二句；还没结束。",
        "尾巴",
    ]
    for start, end, chunk in chunks:
        assert text[start:end] == chunk


def test_build_sentence_chunks_links_back_to_work(tmp_path):
    input_path = tmp_path / "works.jsonl"
    output_path = tmp_path / "chunks.jsonl"
    report_path = tmp_path / "report.json"
    _write_jsonl(
        input_path,
        [
            _work("唐.csv:1", "甲，乙。丙！"),
            _work("宋.csv:1", "没有句号的整段"),
        ],
    )

    report = build_sentence_chunks(
        input_path,
        output_path,
        report_path,
        expected_works=2,
        expected_chunks=3,
    )
    rows = [
        json.loads(line)
        for line in output_path.read_text(encoding="utf-8").splitlines()
    ]

    assert [row["text"] for row in rows] == ["甲，乙。", "丙！", "没有句号的整段"]
    assert rows[0] == {
        "chunk_id": "werneror_poetry:唐.csv:1:sentence:0",
        "work_id": "werneror_poetry:唐.csv:1",
        "policy": "sentence",
        "chunk_index": 0,
        "start": 0,
        "end": 4,
        "text": "甲，乙。",
    }
    assert report["works"] == 2
    assert report["chunks"] == 3
    assert report["works_without_chunks"] == 0
    assert json.loads(report_path.read_text(encoding="utf-8"))["chunks"] == 3


def test_build_sentence_chunks_removes_partial_output_on_count_mismatch(tmp_path):
    input_path = tmp_path / "works.jsonl"
    output_path = tmp_path / "chunks.jsonl"
    _write_jsonl(input_path, [_work("唐.csv:1", "一句。两句。")])

    with pytest.raises(ValueError, match="画像预期"):
        build_sentence_chunks(
            input_path,
            output_path,
            tmp_path / "report.json",
            expected_works=1,
            expected_chunks=99,
        )

    assert not output_path.exists()
    assert not (tmp_path / "chunks.jsonl.tmp").exists()


def test_split_clause_spans_cuts_on_comma_semicolon_and_sentence_end():
    text = "渭城朝雨浥轻尘，客舍青青柳色新。尾句；收束！"
    chunks = list(split_clause_spans(text))

    assert [chunk[2] for chunk in chunks] == [
        "渭城朝雨浥轻尘，",
        "客舍青青柳色新。",
        "尾句；",
        "收束！",
    ]
    for start, end, chunk in chunks:
        assert text[start:end] == chunk


def test_build_clause_chunks_marks_clause_policy(tmp_path):
    input_path = tmp_path / "works.jsonl"
    output_path = tmp_path / "chunks.jsonl"
    report_path = tmp_path / "report.json"
    _write_jsonl(
        input_path,
        [_work("唐.csv:1", "甲，乙。")],
    )

    report = build_clause_chunks(
        input_path,
        output_path,
        report_path,
        expected_works=1,
        expected_chunks=2,
    )
    rows = [
        json.loads(line)
        for line in output_path.read_text(encoding="utf-8").splitlines()
    ]

    assert [row["text"] for row in rows] == ["甲，", "乙。"]
    assert all(row["policy"] == "clause" for row in rows)
    assert report["policy"] == "clause"
