import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path, PurePosixPath
from dataclasses import asdict

from ebooklib import epub

from .epub.reader import parse_toc
from .extractor.extractor import extract_collection
from .extract_images import extract_referenced_images
from .pipeline.normalize import normalize_poems, resolve_mapping, get_output_form


EPUB_PATH = Path("data/raw/历代名家词集精华录.epub")

# These warning kinds contain source paragraphs that are retained by the
# extractor's private section/audit evidence, but deliberately have no slot in
# the public-facing PoemContent schema. Writing normalized JSON would silently
# omit them. Review and classify them before running the import command.
NON_EXPORTABLE_WARNING_TYPES = frozenset({
    "unclassified_after_notes",
    "unclassified_before_inserted_author",
    "ambiguous_reference_after_verse",
})


def ensure_no_unclassified_content(poems):
    """Fail closed before writing a partial extracted/normalized dataset."""
    affected = []
    for poem in poems:
        types = sorted({
            issue.get("type") for issue in poem.warnings
            if issue.get("type") in NON_EXPORTABLE_WARNING_TYPES
        })
        if types:
            affected.append((poem.id, types))
    if not affected:
        return
    kinds = sorted({kind for _, types in affected for kind in types})
    examples = ", ".join(poem_id for poem_id, _ in affected[:5])
    raise RuntimeError(
        f"{len(affected)} 首作品含未分类段落，禁止直接导出，以免丢失原文。"
        f"告警类别：{', '.join(kinds)}；样例：{examples}。"
        "请先运行 scripts.corpus.epub_import.diagnostics.audit_extraction "
        "检查原始 XHTML 并明确分类或排除规则。"
    )



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


def resolve_missing_glyphs(missing, map_path, epub_path=EPUB_PATH):
    """提取未知图片，并让用户在终端中人工确认字形。"""

    for html_name, srcs in missing.items():
        folder = PurePosixPath(html_name).stem
        output_dir = Path("data/raw/extracted_images") / folder

        extract_referenced_images(
            epub_path=epub_path,
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
                "-m",
                "scripts.corpus.epub_import.pipeline.glyph_mapping",
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

    parser.add_argument("--toc")
    parser.add_argument("--author")
    parser.add_argument("--slug")
    parser.add_argument("--glyph-map", type=Path)
    parser.add_argument(
        "--all", action="store_true",
        help="按现有审计范围导入十五册，输出合并的中间 Poem JSON",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="与 --all 合用：只做全量无原文预检，不写任何词文 JSON",
    )
    parser.add_argument(
        "--glyph-map-dir", type=Path,
        default=Path("data/raw/glyph_maps"),
        help="--all 时查找每册已有的图片字映射 JSON 的目录",
    )
    parser.add_argument(
        "--preflight-report", type=Path,
        default=Path("data/reports/epub_import_preflight.json"),
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("data/output"),
    )

    parser.add_argument(
        "--epub",
        type=Path,
        default=EPUB_PATH,
    )

    args = parser.parse_args()

    if args.all:
        if args.toc or args.author or args.slug or args.glyph_map:
            parser.error("--all 不与 --toc/--author/--slug/--glyph-map 合用")
        from .batch_import import run_batch

        book = epub.read_epub(str(args.epub))
        report, paths = run_batch(
            book, parse_toc(book.toc),
            map_dir=args.glyph_map_dir,
            output_dir=args.output_dir,
            report_path=args.preflight_report,
            check_only=args.check,
        )
        print(
            f"检查分册 {report['total_collections']}；"
            f"候选作品 {report['total_candidate_poems']}；"
            f"待解决图片字 {report['total_missing_glyph_sites']}；"
            f"不可导出问题 {report['total_unexportable_issues']}"
        )
        print(f"结构预检报告：{args.preflight_report}（不含原书正文）")
        if not report["ready_to_export"]:
            print("尚未满足批量导出条件；请先处理预检报告中的源位置。")
            raise SystemExit(2)
        if args.check:
            print("预检通过：可以去掉 --check 执行全量导出。")
        else:
            print(
                f"十五册全部导出，共写入 {len(paths)} 个本地文件；"
                f"合并数据：{args.output_dir / 'all_normalized.json'}"
            )
            print("注意：这是中间 Poem JSON，并非前端作品库的最终 schema。")
        return

    if args.check:
        parser.error("--check 仅与 --all 合用")
    if not all((args.toc, args.author, args.slug)):
        parser.error("单册导入要求 --toc、--author、--slug；或使用 --all")
    output_dir = args.output_dir
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

    # Intermediate sections can retain text that PoemContent cannot export.
    ensure_no_unclassified_content(poems)

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
            epub_path=args.epub,
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
