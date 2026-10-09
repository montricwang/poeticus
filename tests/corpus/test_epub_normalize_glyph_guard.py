"""Synthetic glyph references: unresolved mappings must remain unchanged."""

from scripts.corpus.epub_import.pipeline.normalize import normalize_poem


def test_missing_glyph_mapping_preserves_unresolved_warning():
    poem = {
        "id": "synthetic-poem",
        "cipai": "测试词牌",
        "title": None,
        "content": {
            "text": ["没有图片字的正文。"],
            "prefaces": [],
            "annotations": [],
            "commentaries": [],
            "inline_notes": [],
        },
        "warnings": [
            {
                "type": "inline_image",
                "src": "unknown-glyph.png",
                "status": "unresolved",
            }
        ],
    }

    result = normalize_poem(poem, {})
    assert result["warnings"] == [
        {
            "type": "inline_image",
            "src": "unknown-glyph.png",
            "status": "unresolved",
        }
    ]


def test_known_glyph_mapping_keeps_resolution_metadata():
    poem = {
        "id": "synthetic-poem",
        "cipai": None,
        "title": "题{{glyph:glyph.png}}",
        "content": {
            "text": [],
            "prefaces": [],
            "annotations": [],
            "commentaries": [],
            "inline_notes": [],
        },
        "warnings": [
            {
                "type": "inline_image",
                "src": "glyph.png",
                "status": "unresolved",
            }
        ],
    }

    result = normalize_poem(
        poem, {"glyph.png": {"source_form": "龢", "display_form": "和"}}
    )
    assert result["title"] == "题和"
    assert result["warnings"][0] == {
        "type": "inline_image",
        "src": "glyph.png",
        "status": "resolved",
        "source_form": "龢",
        "resolved_form": "和",
        "display_form": "和",
    }
