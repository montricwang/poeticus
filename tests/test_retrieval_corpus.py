import json

from retrieval.corpus import (
    build_chunks,
    load_chinese_poetry,
)


def _sample_work(tmp_path):
    path = tmp_path / "poet.tang.sample.json"
    path.write_text(
        json.dumps(
            [
                {
                    "id": "wangwei-weicheng",
                    "author": "王维",
                    "title": "渭城曲",
                    "paragraphs": [
                        "渭城朝雨浥轻尘，客舍青青柳色新。",
                        "劝君更尽一杯酒，西出阳关无故人。",
                    ],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    works = load_chinese_poetry(
        path,
        dynasty="唐",
        genre="poem",
    )
    return works[0]


def test_chinese_poetry_adapter_keeps_parent_and_source_identity(tmp_path):
    work = _sample_work(tmp_path)

    assert work.source == "chinese-poetry"
    assert work.source_record_id == "wangwei-weicheng"
    assert work.author == "王维"
    assert work.dynasty == "唐"
    assert work.genre == "poem"
    assert work.title == "渭城曲"
    assert work.paragraphs[0] == "渭城朝雨浥轻尘，客舍青青柳色新。"

    again = _sample_work(tmp_path)
    assert again.work_id == work.work_id


def test_chunk_policies_keep_traceable_positions(tmp_path):
    work = _sample_work(tmp_path)

    clauses = build_chunks(work, "clause")
    sentences = build_chunks(work, "sentence")
    pairs = build_chunks(work, "clause_pair")

    assert [chunk.text for chunk in clauses] == [
        "渭城朝雨浥轻尘，",
        "客舍青青柳色新。",
        "劝君更尽一杯酒，",
        "西出阳关无故人。",
    ]
    assert [chunk.text for chunk in sentences] == [
        "渭城朝雨浥轻尘，客舍青青柳色新。",
        "劝君更尽一杯酒，西出阳关无故人。",
    ]
    assert [chunk.text for chunk in pairs] == [
        "渭城朝雨浥轻尘，客舍青青柳色新。",
        "客舍青青柳色新。劝君更尽一杯酒，",
        "劝君更尽一杯酒，西出阳关无故人。",
    ]

    second_clause = clauses[1]
    assert second_clause.work_id == work.work_id
    assert second_clause.positions[0].paragraph_index == 0
    assert second_clause.positions[0].unit_index == 1

    cross_paragraph_pair = pairs[1]
    assert [
        position.paragraph_index
        for position in cross_paragraph_pair.positions
    ] == [0, 1]


def test_directory_loader_respects_top_level_file_pattern(tmp_path):
    top = tmp_path / "poet.tang.0.json"
    top.write_text(
        json.dumps(
            [{"author": "甲", "paragraphs": ["甲句。"]}],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    authors = tmp_path / "authors.tang.json"
    authors.write_text(
        json.dumps([{"name": "不应读取"}], ensure_ascii=False),
        encoding="utf-8",
    )

    nested = tmp_path / "error"
    nested.mkdir()
    (nested / "nested.json").write_text(
        json.dumps(
            [{"author": "乙", "paragraphs": ["乙句。"]}],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    works = load_chinese_poetry(
        tmp_path,
        dynasty="唐",
        file_pattern="poet.tang.*.json",
    )

    assert len(works) == 1
    assert works[0].author == "甲"
