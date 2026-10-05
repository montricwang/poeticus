"""测试只使用虚构字形与备份元数据，不使用商业文本。"""
import json
from copy import deepcopy

import pytest

from scripts.corpus.epub_import.review.import_glyph_backup import import_review_backup
from scripts.corpus.epub_import.import_poems import collect_missing_glyphs
from scripts.corpus.epub_import.pipeline.normalize import normalize_poem


def inputs(tmp_path):
    report = {
        "kind": "private-epub-import-preflight",
        "collections": [
            {"collection": "合成册甲", "slug": "test-a", "missing_glyphs": [
                {"html": "x.html", "src": "rare.png"},
                {"html": "y.html", "src": "rare.png"},
                {"html": "y.html", "src": "variant.png"},
            ]},
            {"collection": "合成册乙", "slug": "test-b", "missing_glyphs": [
                {"html": "z.html", "src": "common.png"},
            ]},
        ],
    }
    backup = {
        "schema": "poeticus-glyph-review-v1",
        "records": [
            {"id": "001", "slug": "test-a", "src": "rare.png"},
            {"id": "002", "slug": "test-a", "src": "variant.png"},
            {"id": "003", "slug": "test-b", "src": "common.png"},
        ],
        "values": {
            "001": {"source_form": "⿰木奇"},
            "002": {"source_form": "𠂉"},
            "003": {"source_form": "⿱上下", "display_form": "卡"},
        },
    }
    report_path = tmp_path / "report.json"
    backup_path = tmp_path / "backup.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    backup_path.write_text(json.dumps(backup, ensure_ascii=False), encoding="utf-8")
    return backup_path, report_path, backup


def test_complete_backup_import_reuses_verified_ids_and_keeps_ids_without_substitute(tmp_path):
    path, report, _ = inputs(tmp_path)
    map_dir = tmp_path / "maps"
    result = import_review_backup(path, report, map_dir)
    assert result == {
        "mapped": 3, "unfilled": [], "ids_only": ["001"], "map_files": 2,
    }
    one = json.loads((map_dir / "test_a.json").read_text(encoding="utf-8"))
    two = json.loads((map_dir / "test_b.json").read_text(encoding="utf-8"))
    assert one["rare.png"]["source_form"] == "⿰木奇"
    assert one["rare.png"]["display_form"] is None
    assert one["variant.png"]["source_form"] == "𠂉"
    assert two["common.png"]["source_form"] == "⿱上下"
    assert two["common.png"]["display_form"] == "卡"
    assert import_review_backup(path, report, map_dir) == result

    poem = {
        "id": "demo-001", "tune": "合成调", "title": None,
        "content": {
            "text": ["合成甲{{glyph:rare.png}}乙"],
            "prefaces": [], "annotations": [], "commentaries": [],
            "inline_notes": [],
        },
        "warnings": [{
            "type": "inline_image", "html": "x.html",
            "src": "rare.png", "category": "text", "status": "unresolved",
        }],
    }
    assert not collect_missing_glyphs([poem], one)
    normalized = normalize_poem(deepcopy(poem), one)
    assert normalized["content"]["text"] == ["合成甲⿰木奇乙"]
    assert normalized["warnings"][0]["status"] == "ids_transcription"
    assert normalized["warnings"][0]["source_form"] == "⿰木奇"
    assert normalized["warnings"][0]["resolved_form"] == "⿰木奇"


def test_backup_rejects_wrong_order_and_missing_ids_before_writing(tmp_path):
    path, report, backup = inputs(tmp_path)
    folder = tmp_path / "maps"
    for altered in (
        {**backup, "records": backup["records"][::-1]},
        {**backup, "values": {"001": backup["values"]["001"]}},
        {**backup, "schema": "not-a-real-schema"},
    ):
        path.write_text(
            json.dumps(altered, ensure_ascii=False), encoding="utf-8"
        )
        with pytest.raises(ValueError):
            import_review_backup(path, report, folder)
        assert not folder.exists()


def test_backup_conflict_never_overwrites_existing_mapping(tmp_path):
    path, report, backup = inputs(tmp_path)
    folder = tmp_path / "maps"
    import_review_backup(path, report, folder)
    original = (folder / "test_a.json").read_bytes()
    changed = deepcopy(backup)
    changed["values"]["001"]["display_form"] = "椅"
    path.write_text(json.dumps(changed, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(RuntimeError, match="冲突"):
        import_review_backup(path, report, folder)
    assert (folder / "test_a.json").read_bytes() == original


def test_backup_empty_value_requires_partial_mode(tmp_path):
    path, report, backup = inputs(tmp_path)
    backup["values"]["001"] = {"source_form": ""}
    path.write_text(json.dumps(backup, ensure_ascii=False), encoding="utf-8")
    folder = tmp_path / "maps"
    with pytest.raises(RuntimeError, match="未填写"):
        import_review_backup(path, report, folder)
    assert not folder.exists()
    result = import_review_backup(path, report, folder, partial=True)
    assert result["mapped"] == 2
    assert result["unfilled"] == ["001"]


def test_backup_never_accepts_unrelated_multi_character_prose_as_a_glyph(tmp_path):
    path, report, backup = inputs(tmp_path)
    backup["values"]["001"] = {"source_form": "一个词组"}
    path.write_text(json.dumps(backup, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="单字或 IDS"):
        import_review_backup(path, report, tmp_path / "maps")
