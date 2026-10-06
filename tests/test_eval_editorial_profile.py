import json
from pathlib import Path

from scripts.evals.profile_editorial_notes import (
    build_profile,
    load_records,
    render_markdown,
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
                "annotations": [],
                "commentaries": ["第一行。\n第二行。"],
            },
        },
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


def test_render_markdown_contains_summary_but_not_unbounded_text():
    records = sample_records()
    records[0]["content"]["annotations"].append("长" * 100)

    profile = build_profile(
        records,
        source_path=Path("private.json"),
        sample_size=1,
        excerpt_chars=20,
        seed=1,
    )
    markdown = render_markdown(profile)

    assert "## annotations" in markdown
    assert "## commentaries" in markdown
    assert "私人诊断报告" in markdown
    assert "长" * 20 + "…" in markdown
    assert "长" * 100 not in markdown


def test_load_records_requires_top_level_array(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"content": {}}), encoding="utf-8")

    try:
        load_records(path)
    except ValueError as exc:
        assert "顶层必须是数组" in str(exc)
    else:
        raise AssertionError("应拒绝非数组顶层")
