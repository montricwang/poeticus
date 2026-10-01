import json
import re
from pathlib import Path


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
    poems = load_json(Path("data/output/wen_tingyun.json"))

    glyph_map = load_json(Path("data/raw/glyph_maps/wen_tingyun.json"))

    normalized = [normalize_poem(poem, glyph_map) for poem in poems]

    unresolved = []

    for poem in normalized:
        for category in ["text", "annotations", "commentaries"]:
            for text in poem["content"][category]:
                if "{{glyph:" in text:
                    unresolved.append(
                        {
                            "poem_id": poem["id"],
                            "category": category,
                            "text": text,
                        }
                    )

    if unresolved:
        print(f"仍有 {len(unresolved)} 处未解析图片字：")

        for item in unresolved:
            print(
                item["poem_id"],
                item["category"],
                item["text"],
            )

        raise RuntimeError("存在未解析的 glyph placeholder")

    output_path = Path("data/output/wen_tingyun_normalized.json")

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(
            normalized,
            f,
            ensure_ascii=False,
            indent=2,
        )

    print(f"规范化完成：{output_path}")
