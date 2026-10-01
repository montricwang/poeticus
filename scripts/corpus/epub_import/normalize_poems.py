import json
import re
from pathlib import Path
import argparse

GLYPH_PATTERN = re.compile(r"\{\{glyph:([^}]+)\}\}")


def load_json(path: Path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def resolve_mapping(src, glyph_map):
    item = glyph_map.get(src)

    if item is None:
        return None

    if "same_as" in item:
        return resolve_mapping(item["same_as"], glyph_map)

    return item


def normalize_text(text, glyph_map):
    def replace(match):
        src = match.group(1)
        mapping = resolve_mapping(src, glyph_map)

        if mapping is None:
            return match.group(0)

        display_form = mapping.get("display_form")

        if not display_form:
            return match.group(0)

        return display_form

    return GLYPH_PATTERN.sub(replace, text)


def normalize_poem(poem, glyph_map):
    for category in ["text", "annotations", "commentaries"]:
        poem["content"][category] = [
            normalize_text(text, glyph_map) for text in poem["content"][category]
        ]

    for warning in poem["warnings"]:
        if warning["type"] != "inline_image":
            continue

        mapping = resolve_mapping(warning["src"], glyph_map)

        if mapping and mapping.get("display_form"):
            warning["status"] = "resolved"
            warning["display_form"] = mapping["display_form"]

    return poem


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--glyph-map", type=Path)

    args = parser.parse_args()

    poems = load_json(args.input)

    glyph_map = load_json(args.glyph_map) if args.glyph_map else {}

    normalized = [normalize_poem(poem, glyph_map) for poem in poems]

    unresolved = []

    for poem in normalized:
        for category in ["text", "annotations", "commentaries"]:
            for text in poem["content"][category]:
                if "{{glyph:" in text:
                    unresolved.append((poem["id"], category, text))

    if unresolved:
        for poem_id, category, text in unresolved:
            print(f"未解析：{poem_id} [{category}] {text}")

        raise RuntimeError(f"仍有 {len(unresolved)} 个段落包含未解析图片字")

    args.output.parent.mkdir(parents=True, exist_ok=True)

    with args.output.open("w", encoding="utf-8") as f:
        json.dump(normalized, f, ensure_ascii=False, indent=2)

    print(f"规范化完成：{len(normalized)} 首")
    print(f"输出文件：{args.output}")
