"""把人工核对过的图片字映射应用到抽取记录。"""

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


def is_ids_form(value):
    """Unicode 表意文字描述序列（IDS），不是统一编码的单个字符。"""
    return bool(
        isinstance(value, str)
        and len(value) >= 3
        and "\u2ff0" <= value[0] <= "\u2fff"
    )


def get_output_form(mapping):
    if not mapping:
        return None
    display = mapping.get("display_form")
    if display:
        return display
    source = mapping.get("source_form") or ""
    # 找不到可靠现代对应字的 IDS 必须继续明确标记为 IDS。
    # 不能为了顺利导出语料而臆造 Unicode 等价字。
    return source if len(source) == 1 or is_ids_form(source) else None


def normalize_text(text, glyph_map):
    def replace(match):
        item = resolve_mapping(match.group(1), glyph_map)
        return get_output_form(item) or match.group(0)

    return GLYPH_PATTERN.sub(replace, text)


def canonicalize_heading_fields(poem):
    """旧版私人导出仍可读取；新 JSON 统一使用正式字段名。"""
    for canonical, legacy in (("cipai", "tune"), ("yusheng_title", "yusheng")):
        if legacy in poem:
            if canonical in poem and poem[canonical] != poem[legacy]:
                raise ValueError(
                    f"{poem.get('id', '?')}: {canonical} 与 {legacy} 的值冲突"
                )
            poem.setdefault(canonical, poem[legacy])
            del poem[legacy]
    return poem


def normalize_poem(poem, glyph_map):
    canonicalize_heading_fields(poem)
    for field in ("cipai", "title", "yusheng_title"):
        if poem.get(field) is not None:
            poem[field] = normalize_text(
                poem[field],
                glyph_map,
            )

    raw_paragraphs = poem["content"].get("text", [])
    # normalize 可能把较长图片字占位符替换成单个字符。
    # 修改正文前必须先重算行内注记 offset，确保区间始终指向 normalize 后的段落。
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

        if mapping is not None and output is not None:
            source_form = mapping.get("source_form")
            warning["source_form"] = source_form
            warning["status"] = (
                "ids_transcription"
                if is_ids_form(source_form) and not mapping.get("display_form")
                else "resolved"
            )
            warning["resolved_form"] = output

            if mapping.get("display_form"):
                warning["display_form"] = mapping["display_form"]

    return poem


def unresolved_glyphs(poems):
    for poem in poems:
        fields = [
            ("cipai", poem.get("cipai")),
            ("title", poem.get("title")),
            ("yusheng_title", poem.get("yusheng_title")),
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
    规范化已抽取的 Poem JSON。

    这是 Pipeline 的正式入口；CLI 只负责包装调用本函数。
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
