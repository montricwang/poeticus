"""Resolve manually reviewed image glyphs in extracted poetry records."""

import argparse
import json
import re
from pathlib import Path


GLYPH_PATTERN = re.compile(r"\{\{glyph:([^}]+)\}\}")


def load_json(path):
    with Path(path).open(encoding="utf-8") as handle:
        return json.load(handle)


def resolve_mapping(src, glyph_map, seen=None):
    seen = set() if seen is None else seen

    if src in seen:
        raise ValueError(f"循环图片字映射：{src}")

    seen.add(src)

    item = glyph_map.get(src)

    if item is None:
        return None

    if "same_as" in item:
        return resolve_mapping(item["same_as"], glyph_map, seen)

    return item


def get_output_form(mapping):
    if not mapping:
        return None

    return mapping.get("display_form") or (
        mapping.get("source_form")
        if len(mapping.get("source_form") or "") == 1
        else None
    )


def normalize_text(text, glyph_map):
    def replace(match):
        item = resolve_mapping(match.group(1), glyph_map)
        return get_output_form(item) or match.group(0)

    return GLYPH_PATTERN.sub(replace, text)


def normalize_poem(poem, glyph_map):
    for field in ("tune", "title"):
        if poem.get(field) is not None:
            poem[field] = normalize_text(
                poem[field],
                glyph_map,
            )

    raw_paragraphs = poem["content"].get("text", [])
    # Normalization can replace a long glyph token with one character.
    # Rebase inline-note offsets *before* changing the body text so the
    # recorded intervals always refer to the normalized paragraph.
    for note in poem["content"].get("inline_notes", []):
        index = note["paragraph_index"]
        if not (0 <= index < len(raw_paragraphs)):
            raise ValueError("行内附注的正文段落号越界")
        raw = raw_paragraphs[index]
        start, end = note["start"], note["end"]
        if not (0 <= start < end <= len(raw)
                and raw[start:end] == note["text"]):
            raise ValueError("行内附注位置与原文不一致；禁止错误导出")
        normalized_before = normalize_text(raw[:start], glyph_map)
        normalized_note = normalize_text(note["text"], glyph_map)
        note["start"] = len(normalized_before)
        note["end"] = note["start"] + len(normalized_note)
        note["text"] = normalized_note

    for category in (
        "text",
        "prefaces",
        "annotations",
        "commentaries",
    ):
        poem["content"][category] = [
            normalize_text(text, glyph_map)
            for text in poem["content"].get(category, [])
        ]
    for note in poem["content"].get("inline_notes", []):
        source = poem["content"]["text"][note["paragraph_index"]]
        if source[note["start"]:note["end"]] != note["text"]:
            raise ValueError("行内附注位置在正文规范化后失效")

    for warning in poem.get("warnings", []):
        if warning.get("type") != "inline_image":
            continue

        mapping = resolve_mapping(
            warning["src"],
            glyph_map,
        )

        output = get_output_form(mapping)

        if output is not None:
            warning["status"] = "resolved"
            warning["resolved_form"] = output

            if mapping.get("display_form"):
                warning["display_form"] = mapping["display_form"]

    return poem


def unresolved_glyphs(poems):
    for poem in poems:
        fields = [
            ("tune", poem.get("tune")),
            ("title", poem.get("title")),
        ]

        fields.extend(
            (
                category,
                text,
            )
            for category in (
                "text",
                "prefaces",
                "annotations",
                "commentaries",
            )
            for text in poem["content"].get(category, [])
        )

        for category, text in fields:
            if text and "{{glyph:" in text:
                yield poem["id"], category, text


def normalize_poems(input_path, output_path, glyph_map=None):
    """
    Normalize extracted poem JSON.

    This is the pipeline entry point.
    CLI only wraps this function.
    """

    poems = load_json(input_path)

    glyph_map = glyph_map or {}

    normalized = [normalize_poem(poem, glyph_map) for poem in poems]

    unresolved = list(unresolved_glyphs(normalized))

    if unresolved:
        for poem_id, category, text in unresolved[:30]:
            print(f"未解析：{poem_id} [{category}] {text[:80]}")

        raise RuntimeError(f"仍有 {len(unresolved)} 个文本字段包含未解析图片字")

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path.write_text(
        json.dumps(
            normalized,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"规范化完成：{len(normalized)} 首；输出：{output_path}")

    return normalized


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--input",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--output",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--glyph-map",
        type=Path,
    )

    args = parser.parse_args()

    glyph_map = load_json(args.glyph_map) if args.glyph_map else {}

    normalize_poems(
        input_path=args.input,
        output_path=args.output,
        glyph_map=glyph_map,
    )


if __name__ == "__main__":
    main()
