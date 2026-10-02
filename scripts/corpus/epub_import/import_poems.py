import argparse
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path, PurePosixPath

from extract_images import extract_referenced_images
from pipeline.normalize import resolve_mapping, get_output_form


EPUB_PATH = Path("data/raw/历代名家词集精华录.epub")


def load_map(path):
    if not path.exists():
        return {}

    with path.open(encoding="utf-8") as f:
        return json.load(f)


def collect_missing_glyphs(poems, glyph_map):
    """根据 Extraction 的 warnings 找出尚未解决的图片字。"""
    missing = defaultdict(set)

    for poem in poems:
        for warning in poem.get("warnings", []):
            if warning["type"] != "inline_image":
                continue

            src = warning["src"]
            mapping = resolve_mapping(src, glyph_map)

            if get_output_form(mapping) is None:
                missing[warning["html"]].add(src)

    return missing


def resolve_missing_glyphs(missing, map_path, script_dir):
    """提取未知图片，并让用户在终端中人工确认字形。"""

    for html_name, srcs in missing.items():
        folder = PurePosixPath(html_name).stem
        output_dir = Path("data/raw/extracted_images") / folder

        extract_referenced_images(
            epub_path=EPUB_PATH,
            html_name=html_name,
            output_dir=output_dir,
            only_srcs=srcs,
        )

        for src in sorted(srcs):
            image_path = output_dir / PurePosixPath(src).name

            print(f"\n待确认图片：{image_path}", flush=True)

            source = input("原字（Unicode 汉字 / IDS / U+编码）：").strip()

            if not source:
                raise RuntimeError(f"{src} 未填写原字，停止导入")

            display = input("替代字（不需要替换直接回车）：").strip()

            command = [
                sys.executable,
                str(script_dir / "pipeline/glyph_mapping.py"),
                str(image_path),
                "--source",
                source,
                "--map",
                str(map_path),
            ]

            if display:
                command.extend(["--display", display])

            subprocess.run(command, check=True)


def print_glyph_summary(poems, glyph_map):
    """打印本次实际使用过的图片字映射。"""
    seen = set()

    print("\n=== 本次图片字处理 ===")

    for poem in poems:
        for warning in poem.get("warnings", []):
            if warning["type"] != "inline_image":
                continue

            src = warning["src"]

            if src in seen:
                continue

            seen.add(src)

            mapping = resolve_mapping(src, glyph_map)
            source = mapping["source_form"]
            output = get_output_form(mapping)

            if mapping.get("display_form"):
                print(f"{src}：{source} → {output}（替换）")
            else:
                print(f"{src}：{source}（保留原字）")

    if not seen:
        print("未发现图片字")


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--toc", required=True)
    parser.add_argument("--author", required=True)
    parser.add_argument("--slug", required=True)
    parser.add_argument("--glyph-map", type=Path)

    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    output_dir = Path("data/output")
    stem = args.slug.replace("-", "_")

    extracted = output_dir / f"{stem}.json"
    normalized = output_dir / f"{stem}_normalized.json"

    # 未指定时自动使用作者对应的映射文件
    map_path = args.glyph_map or Path("data/raw/glyph_maps") / f"{stem}.json"

    # 1. Extraction
    subprocess.run(
        [
            sys.executable,
            str(script_dir / "extractor" / "extractor.py"),
            "--toc",
            args.toc,
            "--author",
            args.author,
            "--slug",
            args.slug,
        ],
        check=True,
    )

    with extracted.open(encoding="utf-8") as f:
        poems = json.load(f)

    # 2. 检查是否有尚未辨认的图片字
    glyph_map = load_map(map_path)
    missing = collect_missing_glyphs(poems, glyph_map)

    # 3. 如果有，让用户人工补充映射
    if missing:
        if not sys.stdin.isatty():
            raise RuntimeError("存在未解析图片字，需要在交互式终端中处理")

        resolve_missing_glyphs(
            missing,
            map_path,
            script_dir,
        )

    # 4. Normalization
    command = [
        sys.executable,
        str(script_dir / "pipeline" / "normalize.py"),
        "--input",
        str(extracted),
        "--output",
        str(normalized),
    ]

    if map_path.exists():
        command.extend(["--glyph-map", str(map_path)])

    subprocess.run(command, check=True)

    # 5. 打印实际使用的字形处理记录
    glyph_map = load_map(map_path)
    print_glyph_summary(poems, glyph_map)

    print(f"\n导入流程完成：{normalized}")


if __name__ == "__main__":
    main()
