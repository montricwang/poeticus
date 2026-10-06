from pathlib import Path

from evals.retrieval_corpus import (
    chunks_for_work,
    load_chinese_poetry_file,
    split_text,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "chinese_poetry_retrieval_sample.json"


def test_clause_chunking_splits_on_minor_and_major_punctuation():
    text = "渭城朝雨浥輕塵，客舍青青柳色新。"

    chunks = split_text(text, "clause")

    assert chunks == ["渭城朝雨浥輕塵，", "客舍青青柳色新。"]


def test_sentence_chunking_keeps_comma_clauses_together():
    text = "渭城朝雨浥輕塵，客舍青青柳色新。勸君更盡一杯酒。"

    chunks = split_text(text, "sentence")

    assert chunks == [
        "渭城朝雨浥輕塵，客舍青青柳色新。",
        "勸君更盡一杯酒。",
    ]


def test_clause_pair_chunking_uses_overlapping_adjacent_clauses():
    text = "甲，乙。丙！"

    chunks = split_text(text, "clause_pair")

    assert chunks == ["甲，乙。", "乙。丙！"]


def test_chinese_poetry_adapter_keeps_source_and_parent_work():
    works = load_chinese_poetry_file(FIXTURE, dynasty="唐")

    first = works[0]
    assert first.author == "王維"
    assert first.title == "渭城曲"
    assert first.dynasty == "唐"
    assert first.source == "chinese-poetry/chinese-poetry"
    assert first.source_record_id == "fixture-wangwei"

    chunks = chunks_for_work(first, "clause")

    assert len(chunks) == 4
    assert {chunk.work_id for chunk in chunks} == {first.id}
    assert all(chunk.source == first.source for chunk in chunks)
    assert [chunk.position for chunk in chunks] == [0, 1, 2, 3]


def test_chinese_poetry_adapter_falls_back_to_rhythmic_and_stable_source_id():
    first_run = load_chinese_poetry_file(FIXTURE, dynasty="宋")
    second_run = load_chinese_poetry_file(FIXTURE, dynasty="宋")

    work = first_run[1]
    assert work.title == "御街行"
    assert work.source_record_id == f"{FIXTURE.name}#1"
    assert work.id == second_run[1].id
