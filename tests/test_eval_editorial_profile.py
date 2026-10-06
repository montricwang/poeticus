import json
from pathlib import Path

from scripts.evals.profile_editorial_notes import (
    build_profile,
    classify_annotation_structure,
    extract_headword,
    load_records,
    render_markdown,
    safe_source_label,
)


def sample_records():
    return [
        {
            "id": "p1",
            "author": "甲",
            "collection": "甲词集",
            "cipai": "某调",
            "title": "其一",
            "content": {
                "text": ["这里有词甲，也有别的正文。"],
                "annotations": ["词甲：解释。", "《某书》有相关记载。"],
                "commentaries": ["这一段用于说明整体写法。"],
            },
        },
        {
            "id": "p2",
            "author": "乙",
            "collection": "乙词集",
            "cipai": "另一调",
            "title": None,
            "content": {
                "text": ["这里仍然出现词甲。"],
                "annotations": ["词甲：解释。", ""],
                "commentaries": [],
            },
        },
        {
            "id": "p3",
            "author": "乙",
            "collection": "乙词集",
            "cipai": "另一调",
            "title": "其二",
            "content": {
                "text": ["普通正文。"],
                "annotations": [],
                "commentaries": ["第一行。\n第二行。"],
            },
        },
    ]


def structural_records():
    return [
        {
            "id": "s1",
            "author": "甲",
            "collection": "甲词集",
            "cipai": "某调",
            "title": None,
            "content": {
                "text": ["轣辘牵金井，另有正文。"],
                "annotations": [
                    "◎轣辘：即辘轳。",
                    "◎双眸翦秋水，十指剥春葱。（唐白居易《筝》）",
                    "◎摩围：见前《踏莎行》注。",
                    "◎" + "本事很长。" * 45,
                    "◎只是普通说明。",
                    "◎别名：这里解释，但正文并无此词。",
                ],
                "commentaries": [],
            },
        }
    ]


def test_build_profile_counts_distribution_and_anomalies(tmp_path):
    source = tmp_path / "normalized.json"
    profile = build_profile(
        sample_records(),
        source_path=source,
        sample_size=2,
        excerpt_chars=40,
        seed=7,
    )

    annotations = profile["categories"]["annotations"]
    commentaries = profile["categories"]["commentaries"]

    assert profile["record_count"] == 3
    assert profile["anomaly_count"] == 1

    assert annotations["item_count"] == 3
    assert annotations["unique_item_count"] == 2
    assert annotations["records_with_items"] == 2
    assert annotations["records_without_items"] == 1
    assert annotations["features"]["contains_colon"]["count"] == 2
    assert annotations["features"]["contains_book_title_marks"]["count"] == 1
    assert annotations["repeated_items"][0]["count"] == 2

    assert commentaries["item_count"] == 2
    assert commentaries["records_with_items"] == 2
    assert commentaries["features"]["contains_newline"]["count"] == 1


def test_collection_profile_uses_record_denominator():
    profile = build_profile(
        sample_records(),
        source_path=Path("private.json"),
        sample_size=1,
        excerpt_chars=40,
        seed=1,
    )
    rows = {
        row["collection"]: row
        for row in profile["categories"]["annotations"]["by_collection"]
    }

    assert rows["甲词集"]["records"] == 1
    assert rows["甲词集"]["items"] == 2
    assert rows["甲词集"]["items_per_record"] == 2.0

    assert rows["乙词集"]["records"] == 2
    assert rows["乙词集"]["records_with_items"] == 1
    assert rows["乙词集"]["items"] == 1
    assert rows["乙词集"]["items_per_record"] == 0.5
    assert rows["乙词集"]["coverage_rate"] == 0.5


def test_annotation_structure_heuristics_are_structural_only():
    profile = build_profile(
        structural_records(),
        source_path=Path("private.json"),
        sample_size=2,
        excerpt_chars=60,
        seed=3,
    )
    structures = profile["categories"]["annotations"]["structure_candidates"]
    counts = {row["structure"]: row["count"] for row in structures["counts"]}

    assert counts == {
        "headword_colon": 2,
        "quoted_source": 1,
        "cross_reference": 1,
        "long_source_note": 1,
        "other": 1,
    }

    headwords = structures["headword_candidates"]
    assert headwords["count"] == 3
    assert headwords["matched_in_body"] == 1
    assert headwords["unmatched_in_body"] == 2


def test_extract_headword_and_cross_reference_precedence():
    assert extract_headword("◎轣辘：即辘轳。") == "轣辘"
    assert extract_headword("◎这是一段很长很长的题头名称超过限制：解释。") is None

    classified = classify_annotation_structure(
        {
            "text": "◎摩围：见前《踏莎行》注。",
            "_body_text": "正文有摩围。",
        }
    )
    assert classified["structure"] == "cross_reference"
    assert classified["headword"] == "摩围"
    assert classified["headword_in_body"] is True


def test_profile_samples_are_deterministic():
    kwargs = {
        "source_path": Path("private.json"),
        "sample_size": 2,
        "excerpt_chars": 40,
        "seed": 11,
    }

    first = build_profile(sample_records(), **kwargs)
    second = build_profile(sample_records(), **kwargs)

    assert (
        first["categories"]["annotations"]["samples"]["random"]
        == second["categories"]["annotations"]["samples"]["random"]
    )
    assert (
        first["categories"]["annotations"]["structure_candidates"]["samples"]
        == second["categories"]["annotations"]["structure_candidates"]["samples"]
    )


def test_render_markdown_contains_refined_annotation_sections():
    profile = build_profile(
        structural_records(),
        source_path=Path("private.json"),
        sample_size=1,
        excerpt_chars=20,
        seed=1,
    )
    markdown = render_markdown(profile)

    assert "### annotation 结构候选" in markdown
    assert "### 冒号前词头候选" in markdown
    assert "按每首元素数排序" in markdown
    assert "带尾部来源的引文" in markdown
    assert "词头命中正文样本" in markdown
    assert "本事很长。" * 45 not in markdown


def test_load_records_requires_top_level_array(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"content": {}}), encoding="utf-8")

    try:
        load_records(path)
    except ValueError as exc:
        assert "顶层必须是数组" in str(exc)
    else:
        raise AssertionError("应拒绝非数组顶层")


def test_safe_source_label_does_not_expose_external_absolute_path(tmp_path):
    external = tmp_path / "private.json"

    assert safe_source_label(external) == "private.json"
