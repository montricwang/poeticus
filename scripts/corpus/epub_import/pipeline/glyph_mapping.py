import argparse
import json
from pathlib import Path

import re


def parse_form(value):
    if value is None:
        return None

    value = value.strip()

    if re.fullmatch(r"U\+[0-9A-Fa-f]{4,6}", value):
        point = int(value[2:], 16)

        if point > 0x10FFFF or 0xD800 <= point <= 0xDFFF:
            raise ValueError(f"无效 Unicode 码位：{value}")

        return chr(point)

    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError("命令行字符传递异常，请改用 U+xxxxx 形式") from exc

    if "\ufffd" in value:
        raise ValueError("检测到替代字符 �，请检查输入")

    return value


def codepoint(char):
    if len(char) == 1:
        return f"U+{ord(char):04X}"
    return None


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("image", type=Path)
    parser.add_argument("--source", required=True)
    parser.add_argument("--display")
    parser.add_argument("--map", type=Path, required=True)

    args = parser.parse_args()

    source = parse_form(args.source)
    display = parse_form(args.display)

    if not source:
        parser.error("--source 不能为空")

    if display and len(display) != 1:
        parser.error("--display 必须是单个 Unicode 字符")

    if not display and len(source) != 1:
        parser.error("原字形为 IDS 时，必须提供 --display")

    if not args.image.is_file():
        parser.error(f"图片不存在：{args.image}")

    entry = {
        "source_form": source,
        "source_codepoint": codepoint(source),
        "display_form": display,
        "display_codepoint": codepoint(display) if display else None,
        "status": "reviewed",
    }

    path = args.map

    if path.exists():
        with path.open(encoding="utf-8") as f:
            glyph_map = json.load(f)
    else:
        glyph_map = {}

    filename = args.image.name

    if filename in glyph_map:
        if glyph_map[filename] == entry:
            print(f"映射已存在：{filename}")
            return

        raise RuntimeError(f"映射冲突，请人工检查：{filename}")

    glyph_map[filename] = entry

    path.parent.mkdir(parents=True, exist_ok=True)

    content = json.dumps(
        glyph_map,
        ensure_ascii=False,
        indent=2,
    )

    temp_path = path.with_suffix(".json.tmp")
    temp_path.write_text(content, encoding="utf-8")
    temp_path.replace(path)

    print(f"已添加映射：{filename}")
    print(json.dumps(entry, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
