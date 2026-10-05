"""Prepare a local glyph gallery and safely apply user-reviewed TSV mappings.

The gallery includes copyrighted image glyphs. Never publish these outputs.
"""
import argparse
import csv
import html
import json
import posixpath
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote

from ebooklib import epub

from ..pipeline.glyph_mapping import codepoint, load_map, parse_form, save_map
from ..pipeline.normalize import is_ids_form


FIELDS = ("index", "slug", "collection", "src", "source_form",
          "display_form", "occurrences")


def glyph_sites(report):
    """One review row for each (volume, source image), not each XHTML usage."""
    cases = {}
    for collection in report["collections"]:
        for site in collection["missing_glyphs"]:
            slug, src, page = collection["slug"], site["src"], site["html"]
            key = (slug, src)
            if key not in cases:
                cases[key] = {"slug": slug, "src": src,
                              "collection": collection["collection"], "pages": []}
            if page not in cases[key]["pages"]:
                cases[key]["pages"].append(page)
    return list(cases.values())


def _epub_image(book, page, src):
    if "://" in src or src.startswith("/"):
        raise ValueError(f"EPUB 图片路径异常：{src}")
    href = posixpath.normpath(posixpath.join(posixpath.dirname(page), src))
    if href.startswith("../"):
        raise ValueError(f"EPUB 图片路径越界：{page} / {src}")
    item = book.get_item_with_href(href)
    if item is None:
        return None
    return item.get_content() if hasattr(item, "get_content") else item.content


def prepare_review(report, book, *, sheet_path, tsv_path):
    """Generate a private gallery and editable TSV, no user input required."""
    sheet_path, tsv_path = Path(sheet_path), Path(tsv_path)
    if sheet_path.resolve() == tsv_path.resolve():
        raise ValueError("HTML 与 TSV 路径不能相同")
    cases = glyph_sites(report)
    if not cases:
        raise ValueError("预检中没有未映射的图片字")
    image_dir = sheet_path.parent / (sheet_path.stem + "_images")
    image_dir.mkdir(parents=True, exist_ok=True)
    tsv_path.parent.mkdir(parents=True, exist_ok=True)
    cards, rows, absent = [], [], []
    for index, case in enumerate(cases, 1):
        label = f"{index:03d}"
        blobs = []
        for page in case["pages"]:
            image = _epub_image(book, page, case["src"])
            if image is not None:
                blobs.append(image)
        if len(set(blobs)) > 1:
            raise RuntimeError(
                f"同一映射键指向不同图片：{case['slug']} / {case['src']}"
            )
        value = blobs[0] if blobs else None
        if value is None:
            absent.append((case["slug"], case["src"]))
            image_html = "<em>图片文件未找到</em>"
        else:
            suffix = Path(case["src"]).suffix.lower()
            if suffix not in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
                suffix = ".bin"
            filename = f"{label}{suffix}"
            (image_dir / filename).write_bytes(value)
            uri = quote(image_dir.name + "/" + filename)
            image_html = (
                f'<a href="{uri}" target="_blank">'
                f'<img loading="lazy" src="{uri}" alt="图片字 {label}"></a>'
            )
        rows.append({
            "index": label, "slug": case["slug"],
            "collection": case["collection"], "src": case["src"],
            "source_form": "", "display_form": "",
            "occurrences": ", ".join(case["pages"]),
        })
        cards.append(
            '<article class="glyph"><b>' + label +
            '</b><div class="image">' + image_html +
            '</div><div><strong>' + html.escape(case["collection"]) +
            '</strong><br><code>' + html.escape(case["src"]) +
            '</code><br><small>' +
            html.escape(", ".join(case["pages"])) +
            '</small></div></article>'
        )

    # Do not discard manually reviewed values on accidental rerun.
    if tsv_path.exists():
        with tsv_path.open(encoding="utf-8-sig", newline="") as stream:
            old = list(csv.DictReader(stream, delimiter="\t"))
        if any((row.get("source_form") or "").strip() for row in old):
            raise RuntimeError(
                f"人工核对表 {tsv_path} 已包含填写内容，拒绝覆盖。"
            )
    with tsv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)

    markup = (
        '<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>EPUB 图片字核对</title><style>'
        'body{font-family:system-ui,sans-serif;max-width:1100px;margin:'
        '28px auto;padding:0 16px;background:#f7f7f7;color:#222}'
        '.grid{display:grid;grid-template-columns:repeat(auto-fill,'
        'minmax(290px,1fr));gap:12px}'
        '.glyph{display:flex;align-items:center;gap:12px;padding:12px;'
        'background:white;border:1px solid #ddd;border-radius:8px}'
        '.image{min-width:85px;min-height:85px;display:grid;'
        'place-items:center;background:#f4f4f4}'
        '.image img{width:80px;height:80px;object-fit:contain;'
        'image-rendering:pixelated}small{color:#666}'
        '</style><h1>EPUB 图片字核对 · ' + str(len(cases)) +
        ' 张</h1><p>本页包含原书图片字，限本地使用。'
        '按编号在 glyph_review.tsv 填写 source_form；'
        '如果原字可直接输入，display_form 留空；'
        '如果原字是 IDS 且暂无可核实的替代字，display_form 可以留空；'
        '中间数据会保留 IDS，并标注其并非 Unicode 单字。'
        '点击图片可查看原图。</p><div class="grid">' +
        "".join(cards) + '</div></html>'
    )
    sheet_path.write_text(markup, encoding="utf-8")
    return {
        "unique_images": len(cases),
        "references": sum(len(c["missing_glyphs"]) for c in report["collections"]),
        "missing_assets": absent,
        "sheet": str(sheet_path), "tsv": str(tsv_path),
    }


def apply_review(tsv_path, *, map_dir, partial=False):
    """Validate all rows before touching any per-collection mapping file."""
    with Path(tsv_path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        if not set(FIELDS).issubset(reader.fieldnames or []):
            raise ValueError("TSV 表头缺少必要列")
        rows = list(reader)
    if not rows:
        raise ValueError("TSV 表没有可核对的字形")
    planned = defaultdict(dict)
    blanks = 0
    for row in rows:
        slug, src = row["slug"].strip(), row["src"].strip()
        source = parse_form(row["source_form"])
        display = parse_form(row["display_form"])
        if not source:
            if display:
                raise ValueError(f"{slug}/{src}: 未填写原字却填写了替代字")
            blanks += 1
            continue
        if len(source) != 1 and not is_ids_form(source):
            raise ValueError(f"{slug}/{src}: 原始字形必须是单字或 IDS")
        if display and len(display) != 1:
            raise ValueError(f"{slug}/{src}: 替代字必须为单个 Unicode 字符")
        value = {
            "source_form": source, "source_codepoint": codepoint(source),
            "display_form": display, "display_codepoint": codepoint(display),
            "status": "reviewed",
        }
        if src in planned[slug] and planned[slug][src] != value:
            raise ValueError(f"{slug}/{src}: 同一图片映射相互冲突")
        planned[slug][src] = value

    if blanks and not partial:
        raise RuntimeError(
            f"还有 {blanks} 张字形未填写；可填写完再执行，"
            "或用 --partial 保存目前已核对部分。"
        )
    changes = {}
    for slug, values in planned.items():
        path = Path(map_dir) / f"{slug.replace('-', '_')}.json"
        old = load_map(path)
        for src, item in values.items():
            if src in old and old[src] != item:
                raise RuntimeError(f"映射冲突：{path} / {src}")
        changes[path] = {**old, **values}
    for path, value in changes.items():
        save_map(path, value)
    return {
        "mapped": sum(len(v) for v in planned.values()),
        "unfilled": blanks, "files_written": len(changes),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--prepare", action="store_true")
    action.add_argument("--contexts", action="store_true",
                        help="从本地 EPUB 按 001–049 编号导出含图片字的完整原文段落")
    action.add_argument("--apply", action="store_true")
    action.add_argument("--import-backup", action="store_true",
                        help="直接导入已填写的 glyph_review_backup.json，无需抄写 TSV")
    parser.add_argument("--epub", type=Path, default=Path(
        "data/raw/历代名家词集精华录.epub"
    ))
    parser.add_argument("--report", type=Path, default=Path(
        "data/reports/epub_import_preflight.json"
    ))
    parser.add_argument("--html", type=Path, default=Path(
        "data/reports/glyph_review.html"
    ))
    parser.add_argument("--tsv", type=Path, default=Path(
        "data/reports/glyph_review.tsv"
    ))
    parser.add_argument("--backup", type=Path, default=Path(
        "data/reports/glyph_review_backup.json"
    ))
    parser.add_argument("--context-html", type=Path, default=Path(
        "data/reports/glyph_contexts.html"
    ))
    parser.add_argument("--map-dir", type=Path, default=Path(
        "data/raw/glyph_maps"
    ))
    parser.add_argument("--partial", action="store_true",
                        help="保存已填写部分的映射")
    args = parser.parse_args()
    if args.prepare or args.contexts:
        if args.partial:
            parser.error("--partial 只能与 --apply 同时使用")
        report = json.loads(args.report.read_text(encoding="utf-8"))
        if report.get("kind") != "private-epub-import-preflight":
            parser.error("报告不是 --all --check 的预检输出")
        book = epub.read_epub(str(args.epub))
        if args.contexts:
            from .glyph_contexts import write_contexts
            path = write_contexts(report, book, args.context_html)
            print(f"已保存包含原书完整段落的私有核对页面：{path}")
            print("每张图片与 glyph_review.html/TSV 使用相同编号；"
                  "不会覆盖已有填写结果。")
        else:
            result = prepare_review(
                report, book, sheet_path=args.html, tsv_path=args.tsv,
            )
            print(
                f"已准备 {result['unique_images']} 张不同图片字，"
                f"来自 {result['references']} 个 XHTML 引用"
            )
            print(f"字形图版：{result['sheet']}")
            print(f"人工填写表：{result['tsv']}")
            if result["missing_assets"]:
                print("以下图片未在 EPUB 找到，请检查其路径：")
                for slug, src in result["missing_assets"]:
                    print(f"  {slug} / {src}")
    elif args.import_backup:
        from .import_glyph_backup import import_review_backup
        result = import_review_backup(
            args.backup, args.report, args.map_dir, partial=args.partial
        )
        print(
            f"已导入 {result['mapped']} 个编号；"
            f"更新分册 glyph 映射文件 {result['map_files']} 个；"
            f"未填写 {len(result['unfilled'])} 个"
        )
        if result["ids_only"]:
            print(
                "仅有 IDS、无 Unicode 替代字的编号："
                + ", ".join(result["ids_only"])
                + "。中间 JSON 将保留 IDS 文本和原图来源，"
                  "不会凭空指定现代通行字。"
            )
    else:
        result = apply_review(
            args.tsv, map_dir=args.map_dir, partial=args.partial,
        )
        print(
            f"已保存 {result['mapped']} 个映射，"
            f"尚有 {result['unfilled']} 个未填写；"
            f"更新 {result['files_written']} 个分册映射文件"
        )


if __name__ == "__main__":
    main()
