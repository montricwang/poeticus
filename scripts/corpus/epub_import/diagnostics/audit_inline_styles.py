"""Audit inline styling and editorial lacuna markers in local EPUB verses.

The generated report contains locations and style metadata ONLY, never any
commercially published verse, note, or commentary text. This is a diagnostic,
not a correction rule: do not automatically remove detected phrases.
"""
import argparse
from collections import Counter
from pathlib import Path

from bs4 import BeautifulSoup
from ebooklib import epub

from ..epub.reader import parse_toc
from ..extractor.blocks import iter_source_blocks
from ..extractor.extractor import extract_collection, extract_sections, raw_xhtml
from ..extractor.rules import INLINE_EDITORIAL_GAP, is_inline_styled_span
from ..config import COLLECTIONS


def _style_signature(span):
    # CSS-only summary; never include the span's text.
    classes = ",".join(span.get("class", [])) or "-"
    style = span.get("style", "").replace("\n", " ").strip() or "-"
    return f"span class={classes} style={style[:120]}"


def collect_inline_evidence(book, toc, collection_specs=COLLECTIONS):
    """Inspect warned verse spans AND parenthesized lacunae in unflagged verse.

    Distinguishes:
    - a paragraph triggering inline_body_style_review;
    - the literal (以下缺) marker occurring anywhere in a verse paragraph;
    - the entire marker lying inside a styled span (not guaranteed to be the
      span that triggered the extractor's warning).
    """
    rows = []
    total_text_blocks = 0
    for collection, author, slug in collection_specs:
        poems, files = extract_collection(book, toc, collection, slug, author)
        sections = [
            section for filename in files
            for section in extract_sections(book, filename, collection=collection)
        ]
        if len(poems) != len(sections):
            raise RuntimeError(f"{collection}: poem/section order mismatch")
        roles = {}
        warned_sites = set()
        for poem, section in zip(poems, sections):
            for entry in section["blocks"]:
                roles[(section["html"], entry["block"])] = entry["role"]
            for warning in poem.warnings:
                if warning.get("type") == "inline_body_style_review":
                    warned_sites.add((warning.get("html"), warning.get("block")))
        for filename in files:
            item = book.get_item_with_href(filename)
            if item is None:
                raise ValueError(f"EPUB XHTML not found: {filename}")
            soup = BeautifulSoup(raw_xhtml(item), "lxml")
            for block in iter_source_blocks(soup, filename):
                if roles.get((filename, block.ordinal)) != "text":
                    continue
                total_text_blocks += 1
                flagged = (filename, block.ordinal) in warned_sites
                has_gap_marker = bool(INLINE_EDITORIAL_GAP.search(block.text))
                if not (flagged or has_gap_marker):
                    continue
                all_spans = list(block.element.find_all("span"))
                styled_spans = [span for span in all_spans if is_inline_styled_span(span)]
                marked_spans = [
                    span for span in styled_spans
                    if INLINE_EDITORIAL_GAP.search(span.get_text("", strip=True))
                ]
                rows.append({
                    "collection": collection,
                    "html": filename,
                    "block": block.ordinal,
                    "paragraph_classes": list(block.classes),
                    "warned": flagged,
                    "has_gap_marker": has_gap_marker,
                    "gap_inside_styled_span": bool(marked_spans),
                    "styled_spans": len(styled_spans),
                    "style_signatures": sorted({
                        _style_signature(span) for span in styled_spans
                    }),
                })
    style_counts = Counter(
        signature for row in rows if row["warned"]
        for signature in row["style_signatures"]
    )
    return {
        "total_text_blocks": total_text_blocks,
        "warned_blocks": sum(row["warned"] for row in rows),
        "gap_marker_blocks": sum(row["has_gap_marker"] for row in rows),
        "gap_marker_warned_blocks": sum(
            row["has_gap_marker"] and row["warned"] for row in rows
        ),
        "gap_marker_inside_styled_span_blocks": sum(
            row["has_gap_marker"] and row["gap_inside_styled_span"]
            for row in rows
        ),
        "style_counts": dict(style_counts.most_common()),
        "sites": rows,
    }


def render_md(report):
    """Shareable positions-only summary, without literary source excerpts."""
    sites = report["sites"]
    marker_sites = [site for site in sites if site["has_gap_marker"]]
    style_sites = [site for site in sites if site["warned"]]
    lines = [
        "# EPUB 正文行内样式与残缺标记审计（仅结构，不含原文）",
        "",
        f"正文源块：{report['total_text_blocks']}；"
        f"特殊字体告警源块：{report['warned_blocks']}；"
        f"包含“（以下缺）”形式的源块：{report['gap_marker_blocks']}。",
        "",
        "包含残缺标记且有样式告警："
        f"{report['gap_marker_warned_blocks']}；"
        "残缺标记整体在带样式 span 内："
        f"{report['gap_marker_inside_styled_span_blocks']}。",
        "",
        "**重要：段落出现特殊 span 不等于残缺标记本身使用了特殊字体；"
        "即使残缺标记在 span 中，也不代表阅读器呈现明显差异。"
        "这里只报告 XHTML 证据，不决定如何拆分正文。**",
        "",
        "## 带样式 span 的结构类型",
        "",
        "| XHTML span 属性（无正文） | 告警段落数 |",
        "|---|---:|",
    ]
    if report["style_counts"]:
        for signature, count in report["style_counts"].items():
            lines.append(f"| {signature.replace('|', '/')} | {count} |")
    else:
        lines.append("| （无） | 0 |")
    lines.extend([
        "",
        "## 残缺标记所在位置（全部）",
        "",
        "| 分册 | XHTML | 块号 | 是否伴随样式告警 | 标记整体位于带样式 span |",
        "|---|---|---:|---|---|",
    ])
    if not marker_sites:
        lines.append("| （无） | — | — | — | — |")
    for site in marker_sites:
        lines.append(
            f"| {site['collection']} | \`{site['html']}\` | "
            f"{site['block']} | {'是' if site['warned'] else '否'} | "
            f"{'是' if site['gap_inside_styled_span'] else '否'} |"
        )
    lines.extend([
        "",
        "## 样式告警位置（每册前 5 处）",
        "",
        "| 分册 | XHTML | 块号 | 段落 class | 带样式 span 数 |",
        "|---|---|---:|---|---:|",
    ])
    shown = Counter()
    for site in style_sites:
        collection = site["collection"]
        if shown[collection] >= 5:
            continue
        shown[collection] += 1
        lines.append(
            f"| {collection} | \`{site['html']}\` | "
            f"{site['block']} | "
            f"{','.join(site['paragraph_classes']) or '-'} | "
            f"{site['styled_spans']} |"
        )
    if not style_sites:
        lines.append("| （无） | — | — | — | — |")
    lines.extend([
        "",
        "复核方式：如需准确判断某一处，将上表的文件名与块号传入 "
        "\`inspect_source --show-html\`，查看原始 span 和周围段落。",
        "",
    ])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--epub", type=Path, default=Path(
        "data/raw/历代名家词集精华录.epub"
    ))
    parser.add_argument("--book", help="可选：只检查某一完整分册名称")
    parser.add_argument("--output", type=Path, default=Path(
        "data/reports/epub_inline_style_audit.md"
    ))
    args = parser.parse_args()
    selected = [
        entry for entry in COLLECTIONS
        if not args.book or entry[0] == args.book
    ]
    if not selected:
        parser.error(f"未找到分册：{args.book}")
    book = epub.read_epub(str(args.epub))
    report = collect_inline_evidence(book, parse_toc(book.toc), selected)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_md(report), encoding="utf-8")
    print(f"行内样式与残缺标记审计：{args.output}")
    print(
        f"特殊字体告警 {report['warned_blocks']} 块；"
        f"（以下缺）标记 {report['gap_marker_blocks']} 块"
    )


if __name__ == "__main__":
    main()
