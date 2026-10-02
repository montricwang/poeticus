import argparse
import json
import re
from pathlib import Path


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
    if char and len(char) == 1:
        return f"U+{ord(char):04X}"

    return None


def load_map(path):
    if path.exists():
        with path.open(encoding="utf-8") as f:
            return json.load(f)

    return {}


def save_map(path, glyph_map):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    content = json.dumps(
        glyph_map,
        ensure_ascii=False,
        indent=2,
    )

    temp_path = path.with_suffix(".json.tmp")
    temp_path.write_text(
        content,
        encoding="utf-8",
    )
    temp_path.replace(path)


def find_same_source(glyph_map, source):
    """
    查找当前 glyph_map 中已经确认过的相同来源字形。
    """
    results = []

    for filename, item in glyph_map.items():
        if item.get("source_form") == source:
            results.append((filename, item))

    return results


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "image",
        type=Path,
    )

    parser.add_argument(
        "--source",
        required=True,
    )

    parser.add_argument(
        "--display",
    )

    parser.add_argument(
        "--map",
        type=Path,
        required=True,
    )

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

    glyph_map = load_map(args.map)

    filename = args.image.name

    if filename in glyph_map:
        existing = glyph_map[filename]

        if existing.get("source_form") == source:
            print(f"映射已存在：{filename}")
            return

        raise RuntimeError(f"映射冲突，请人工检查：{filename}")

    # 检查同来源字形
    same_source = find_same_source(
        glyph_map,
        source,
    )

    if same_source:
        print("\n发现已有相同来源字形：")

        for old_filename, old_item in same_source:
            print(f"  {old_filename}: {old_item.get('display_form')}")

        # 如果已有映射结果一致，可以复用
        if all(item.get("display_form") == display for _, item in same_source):
            answer = input("是否引用已有映射？(y/N): ").strip().lower()

            if answer == "y":
                glyph_map[filename] = {"same_as": same_source[0][0]}

                save_map(
                    args.map,
                    glyph_map,
                )

                print(f"已添加别名映射：{filename} -> {same_source[0][0]}")
                return

        else:
            raise RuntimeError(
                "发现相同 source_form 但 display_form 不一致，请人工检查"
            )

    entry = {
        "source_form": source,
        "source_codepoint": codepoint(source),
        "display_form": display,
        "display_codepoint": codepoint(display),
        "status": "reviewed",
    }

    glyph_map[filename] = entry

    save_map(
        args.map,
        glyph_map,
    )

    print(f"已添加映射：{filename}")

    print(
        json.dumps(
            entry,
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
