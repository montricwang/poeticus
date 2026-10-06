import json

from scripts.corpus.werneror_profile import profile_corpus


def _write_jsonl(path, records):
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records),
        encoding="utf-8",
    )


def _work(record_id, title, dynasty, author, content):
    return {
        "work_id": f"werneror_poetry:{record_id}",
        "title": title,
        "dynasty": dynasty,
        "author": author,
        "content": content,
        "source": "werneror_poetry",
        "source_record_id": record_id,
    }


def test_profile_describes_lengths_chunks_quality_and_coverage(tmp_path):
    path = tmp_path / "works.jsonl"
    _write_jsonl(
        path,
        [
            _work("唐.csv:1", "甲", "唐", "某甲", "春水碧于天，画船听雨眠。"),
            _work("唐.csv:2", "乙", "唐", "某乙", "短句？"),
            _work("宋.csv:1", "丙", "宋", "某丙", "缺字??。\n还有一句。"),
            _work("宋.csv:2", "丙", "宋", "某丙", "缺字??。\n还有一句。"),
        ],
    )

    report = profile_corpus(
        path,
        probes={
            "存在": "春水碧于天，画船听雨眠",
            "不存在": "绝对找不到的句子",
        },
    )

    assert report["records"] == 4
    assert report["dynasties"] == 2
    assert report["authors"] == 3
    assert report["by_dynasty"] == {"唐": 2, "宋": 2}
    assert report["authors_by_dynasty"] == {"唐": 2, "宋": 1}
    assert report["works_with_newline"] == 2
    assert report["estimated_chunks"]["clause"] == 7
    assert report["estimated_chunks"]["sentence"] == 6
    assert report["question_marks"]["works"] == 2
    assert report["question_marks"]["characters"] == 4
    assert report["question_marks"]["works_by_count"] == {"2": 2}
    assert report["exact_duplicates"]["duplicate_records"] == 1
    assert report["exact_duplicates"]["groups"] == 1
    assert len(report["exact_duplicates"]["examples"][0]) == 2
    assert report["coverage_probes"]["存在"]["found"] is True
    assert report["coverage_probes"]["不存在"]["found"] is False


def test_profile_reports_length_percentiles(tmp_path):
    path = tmp_path / "works.jsonl"
    _write_jsonl(
        path,
        [
            _work(f"唐.csv:{i}", f"题{i}", "唐", "作者", "字" * i)
            for i in range(1, 11)
        ],
    )

    report = profile_corpus(path, probes={"x": "不存在"})
    assert report["content_length_chars"] == {
        "min": 1,
        "median": 5,
        "p90": 9,
        "p99": 10,
        "max": 10,
    }
