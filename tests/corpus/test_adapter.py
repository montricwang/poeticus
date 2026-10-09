"""使用无版权风险的合成数据测试中间记录到阅读记录的 adapter。"""
from copy import deepcopy
from typing import NotRequired, TypedDict

import pytest
from pydantic import TypeAdapter
from scripts.corpus.adapter import convert_record, convert_corpus


class ExampleContent(TypedDict):
    text: list[str]
    prefaces: list[str]
    inline_notes: list[dict[str, object]]
    annotations: list[str]
    commentaries: list[str]


class ExampleRecord(TypedDict):
    id: str
    collection: str
    author: str
    title: str | None
    source: str
    content: ExampleContent
    tune: NotRequired[str | None]
    yusheng: NotRequired[str | None]
    cipai: NotRequired[str | None]
    yusheng_title: NotRequired[str | None]


_RECORD_ADAPTER = TypeAdapter(ExampleRecord)

# Adapter 的正式 API 接收可变 dict；这里复制已校验的 TypedDict 测试数据，
# 保留原始字段，不改变数据内容。


def example(**kw: object) -> ExampleRecord:
    """在 Adapter 测试中使用合成来源记录前，先校验其结构。"""
    r: dict[str, object] = {"id": "mock-001", "collection": "合成词集", "author": "词人甲",
         "tune": "某调", "title": None, "source": "合成版", "yusheng": None,
         "content": {
             "text": ["甲乙，丙丁。", "戊己，庚辛。"],
             "prefaces": ["合成小序"], "inline_notes": [],
             "annotations": ["私有注释不可发布"], "commentaries": ["私有评论不可发布"],
         }}
    r.update(kw)
    return _RECORD_ADAPTER.validate_python(r)


def test_preserve_default_and_order_without_modifying_input():
    original = example()
    copy = deepcopy(original)
    records = convert_corpus([original, example(id="mock-002")])
    assert [v.reader["source_order"] for v in records] == [1, 2]
    assert records[0].reader["body_segments"] == original["content"]["text"]
    assert records[0].reader["prefaces"] == ["合成小序"]
    assert "tune" in original
    assert records[0].reader["cipai"] == original["tune"]
    assert "tune" not in records[0].reader
    assert records[0].reader["yusheng_title"] is None
    assert "yusheng" not in records[0].reader
    assert records[0].source["original_segments"] == original["content"]["text"]
    assert "annotations" not in records[0].reader
    assert "commentaries" not in records[0].source
    assert original == copy


def test_join_li_preserving_source_and_segment_boundary():
    r = example(
        collection="李清照词集", author="李清照",
        content={**example()["content"], "text": ["甲，", "乙。", "", "丙，", "丁。"]},
    )
    output = convert_record(dict(r), 1)
    assert output.reader["body_segments"] == ["甲，乙。", "丙，丁。"]
    assert output.source["original_segments"] == r["content"]["text"]
    assert "join_li_qingzhao_lines" in output.actions


def test_southern_tang_newline_and_gap_rebase():
    r = example(
        author="李煜", content={**example()["content"],
        "text": ["甲，\n乙。（以下缺十二字）\n丙。"]},
    )
    output = convert_record(dict(r), 1)
    assert output.reader["body_segments"] == ["甲，乙。（以下缺十二字）丙。"]
    gap = output.reader["lacunae"][0]
    segment = output.reader["body_segments"][gap["segment_index"]]
    assert segment[gap["start"]:gap["end"]] == gap["quote"] == "（以下缺十二字）"
    assert gap["source_position"]["start"] == 5


def test_note_offsets_rebase_after_merge():
    r = example(
        collection="李清照词集", content={**example()["content"], "text": [
            "甲，", "乙【注记】丙。", "", "丁。"
        ], "inline_notes": [{"paragraph_index": 1, "start": 1, "end": 5,
                             "text": "【注记】", "origin": "unverified"}]},
    )
    output = convert_record(dict(r), 1)
    note = output.reader["inline_notes"][0]
    assert (note["segment_index"], note["start"], note["end"]) == (0, 3, 7)
    assert output.reader["body_segments"][0][note["start"]:note["end"]] == "【注记】"


def test_note_offsets_rebase_after_newline_removal():
    r = example(
        author="李璟", content={**example()["content"],
            "text": ["甲，\n乙【注记】丙。"],
            "inline_notes": [{"paragraph_index": 0, "start": 4, "end": 8,
                              "text": "【注记】"}]},
    )
    output = convert_record(dict(r), 1)
    note = output.reader["inline_notes"][0]
    assert note["start"] == 3
    assert output.reader["body_segments"][0][note["start"]:note["end"]] == "【注记】"


def test_stale_note_and_duplicate_source_id_fail_closed():
    bad = example(content={**example()["content"], "inline_notes": [
        {"paragraph_index": 0, "start": 0, "end": 2, "text": "不匹配"}
    ]})
    with pytest.raises(ValueError, match="原始注记文字不匹配"):
        convert_record(dict(bad), 1)
    with pytest.raises(ValueError, match="重复来源 ID"):
        convert_corpus([example(), example()])


def test_source_digest_detects_change_but_not_modern_commentary():
    original = example()
    updated = deepcopy(original)
    updated["content"]["text"][0] = "正文更改"
    comment = deepcopy(original)
    comment["content"]["commentaries"].append("新评论")
    first = convert_record(dict(original), 1).source["source_sha256"]
    assert first != convert_record(dict(updated), 1).source["source_sha256"]
    assert first == convert_record(dict(comment), 1).source["source_sha256"]


def test_reject_li_edge_separator():
    r = example(collection="李清照词集",
                content={**example()["content"], "text": ["", "甲。"]})
    with pytest.raises(ValueError, match="首尾空段"):
        convert_record(dict(r), 1)


def test_legacy_epub_yusheng_becomes_reader_yusheng_title_without_changing_source_digest():
    source = example(yusheng="合成寓声名")
    converted = convert_record(dict(source), 1)
    assert converted.reader["yusheng_title"] == "合成寓声名"
    assert "yusheng" not in converted.reader
    assert "yusheng" in source
    assert source["yusheng"] == "合成寓声名"
    assert converted.source["source_sha256"] == convert_record(dict(source), 1).source["source_sha256"]

def test_old_and_new_heading_keys_have_the_same_stable_source_digest():
    legacy = example(tune="思越人", yusheng="翦朝霞", title="牡丹")
    modern = deepcopy(legacy)
    modern["cipai"] = modern.pop("tune")
    modern["yusheng_title"] = modern.pop("yusheng")
    old = convert_record(dict(legacy), 1)
    new = convert_record(dict(modern), 1)
    assert old.reader == new.reader
    assert old.source["source_sha256"] == new.source["source_sha256"]


def test_conflicting_heading_aliases_refused():
    bad = example(cipai="菩萨蛮", yusheng_title="其他别名")
    with pytest.raises(ValueError, match="cipai 与 tune"):
        convert_record(dict(bad), 1)
    bad = example(yusheng_title="不是原名")
    with pytest.raises(ValueError, match="yusheng_title 与 yusheng"):
        convert_record(dict(bad), 1)
