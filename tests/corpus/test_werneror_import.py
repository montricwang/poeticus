import csv
import json

import pytest

from scripts.corpus.werneror_import import build_corpus


HEADERS = ("题目", "朝代", "作者", "内容")


def _write_csv(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(rows)


def test_build_corpus_preserves_text_and_provenance(tmp_path):
    source = tmp_path / "Poetry"
    source.mkdir()
    _write_csv(
        source / "唐.csv",
        [
            {"题目": "甲", "朝代": "唐", "作者": "某甲", "内容": "上句，下句。"},
            {"题目": "乙", "朝代": "唐", "作者": "某乙", "内容": "第一行。\n第二行？"},
        ],
    )
    _write_csv(
        source / "宋_1.csv",
        [
            {"题目": "甲", "朝代": "唐", "作者": "某甲", "内容": "上句，下句。"},
            {"题目": "", "朝代": "宋", "作者": "", "内容": "缺字?"},
        ],
    )
    # Werneror's own merge script may create this headerless file; ignore it.
    (source / "poetry.csv").write_text("not,a,source,file\n", encoding="utf-8")

    output = tmp_path / "works.jsonl"
    report_path = tmp_path / "report.json"
    report = build_corpus(source, output, report_path, expected_count=4)

    records = [
        json.loads(line)
        for line in output.read_text(encoding="utf-8").splitlines()
    ]
    assert len(records) == 4
    assert records[0] == {
        "work_id": "werneror_poetry:唐.csv:1",
        "title": "甲",
        "dynasty": "唐",
        "author": "某甲",
        "content": "上句，下句。",
        "source": "werneror_poetry",
        "source_record_id": "唐.csv:1",
    }
    assert records[1]["content"] == "第一行。\n第二行？"
    assert records[2]["source_record_id"] == "宋_1.csv:1"

    assert report["records"] == 4
    assert report["by_file"] == {"唐.csv": 2, "宋_1.csv": 2}
    assert report["empty_fields"] == {"title": 1, "author": 1}
    assert report["question_mark_records"] == 1
    assert report["duplicate_exact_records"] == 1
    assert report["excluded_csv"] == ["poetry.csv"]
    assert json.loads(report_path.read_text(encoding="utf-8"))["records"] == 4


def test_build_corpus_rejects_unexpected_headers(tmp_path):
    source = tmp_path / "Poetry"
    source.mkdir()
    (source / "唐.csv").write_text(
        "题目,朝代,作者,正文\n甲,唐,某甲,正文\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="CSV 表头"):
        build_corpus(
            source,
            tmp_path / "works.jsonl",
            tmp_path / "report.json",
            expected_count=None,
        )


def test_build_corpus_removes_partial_output_on_count_mismatch(tmp_path):
    source = tmp_path / "Poetry"
    source.mkdir()
    _write_csv(
        source / "唐.csv",
        [{"题目": "甲", "朝代": "唐", "作者": "某甲", "内容": "正文"}],
    )
    output = tmp_path / "works.jsonl"

    with pytest.raises(ValueError, match="作品总数"):
        build_corpus(
            source,
            output,
            tmp_path / "report.json",
            expected_count=2,
        )

    assert not output.exists()
    assert not (tmp_path / "works.jsonl.tmp").exists()
