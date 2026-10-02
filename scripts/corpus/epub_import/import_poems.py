import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path, PurePosixPath
from dataclasses import asdict

from ebooklib import epub

from epub.reader import parse_toc
from extractor.extractor import extract_collection
from extract_images import extract_referenced_images
from pipeline.normalize import normalize_poems, resolve_mapping, get_output_form


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

            # glyph_mapping 目前仍作为独立人工工具运行
            command = [
                sys.executable,
                str(script_dir / "pipeline" / "glyph_mapping.py"),
                str(image_path),
                "--source",
                source,
                "--map",
                str(map_path),
            ]

            if display:
                command.extend(["--display", display])

            import subprocess

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

    parser.add_argument(
        "--epub",
        type=Path,
        default=EPUB_PATH,
    )

    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent

    output_dir = Path("data/output")
    output_dir.mkdir(parents=True, exist_ok=True)

    stem = args.slug.replace("-", "_")

    extracted = output_dir / f"{stem}.json"
    normalized = output_dir / f"{stem}_normalized.json"

    map_path = args.glyph_map or Path("data/raw/glyph_maps") / f"{stem}.json"

    # 1. EPUB extraction
    book = epub.read_epub(str(args.epub))

    poems, files = extract_collection(
        book,
        parse_toc(book.toc),
        args.toc,
        args.slug,
        args.author,
    )

    if not poems:
        raise RuntimeError("没有抽取到任何作品")

    extracted.write_text(
        json.dumps(
            [asdict(poem) for poem in poems],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"处理 XHTML：{len(files)} 个；抽取作品：{len(poems)} 首；输出：{extracted}")

    # 2. 检查图片字
    poems_data = json.loads(extracted.read_text(encoding="utf-8"))

    glyph_map = load_map(map_path)

    missing = collect_missing_glyphs(
        poems_data,
        glyph_map,
    )

    if missing:
        if not sys.stdin.isatty():
            raise RuntimeError("存在未解析图片字，需要在交互式终端中处理")

        resolve_missing_glyphs(
            missing,
            map_path,
            script_dir,
        )

    # 3. normalization
    glyph_map = load_map(map_path)

    normalize_poems(
        input_path=extracted,
        output_path=normalized,
        glyph_map=glyph_map if map_path.exists() else None,
    )

    # 4. summary
    print_glyph_summary(
        poems_data,
        glyph_map,
    )

    print(f"\n导入流程完成：{normalized}")


if __name__ == "__main__":
    main()
