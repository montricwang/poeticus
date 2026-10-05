"""快速检查本地 EPUB 来源块，同时显示上下文标记与分类角色。

This is a PRIVATE read-only diagnostic. It can display commercially published
text and should never be committed as a fixture or an automated CI artifact.
"""
import argparse
from pathlib import Path

from bs4 import BeautifulSoup
from ebooklib import epub

from ..extractor.blocks import iter_source_blocks
from ..extractor.extractor import extract_sections, raw_xhtml
from ..extractor.rules import is_chronology
from .inspect_dom_hierarchy import _path


def inspect_source(book, html_name, targets=(), *, find=(), collection="",
                   before=2, after=4, max_chars=300, show_html=False):
    """返回便于人工阅读的 Markdown 来源与分类视图。

    Block ordinals are identical to the 15-volume audit's h1/h2/h4/p numbers.
    No file is written here: the caller decides whether to save the report.
    """
    if min(before, after, max_chars) < 0:
        raise ValueError("before/after/max_chars must be non-negative")
    item = book.get_item_with_href(html_name)
    if item is None:
        raise ValueError(f"XHTML 不存在：{html_name}")
    soup = BeautifulSoup(raw_xhtml(item), "lxml")
    blocks = list(iter_source_blocks(soup, html_name))
    indexed = {b.ordinal: b for b in blocks}

    # 可以混用多个 --block 与 --find，并对结果去重。
    found = [
        b.ordinal for b in blocks
        if any(phrase in b.text for phrase in find)
    ]
    selected = sorted(set(targets) | set(found))
    if not selected:
        raise ValueError("没有匹配段落：请核实块号或搜索文字")
    invalid = [n for n in selected if n not in indexed]
    if invalid:
        raise ValueError(f"{html_name} 不包含这些块号：{invalid}")
    if len(selected) > 40:
        raise ValueError("本次目标超过 40 块，请缩小查询范围")

    evidence = {}
    if collection:
        for section in extract_sections(book, html_name, collection=collection):
            for record in section["blocks"]:
                evidence[record["block"]] = (
                    record["role"], section["tune"], section.get("title")
                )

    lines = [
        "# EPUB 原始段落快速查询（仅保存在本地）",
        "",
        f"来源 XHTML：§{html_name}§；总块数：{len(blocks)}；"
        f"目标：{', '.join(str(n) for n in selected)}。",
        "",
        "**注意：报告包含原书文字，仅用于本地人工核对；"
        "不得直接提交到公开 GitHub。**",
        "",
    ]
    for number in selected:
        b = indexed[number]
        lo = max(1, number - before)
        hi = min(len(blocks), number + after)
        lines.extend([
            f"## 目标块 {number} · {b.tag}",
            "",
            f"DOM：§{_path(b.element)}§",
            "",
            f"附近块：{lo}–{hi}（目标用 ★ 标记）",
            "",
        ])
        for pos in range(lo, hi + 1):
            block = indexed[pos]
            css = ".".join(block.classes)
            tag = block.tag + ("." + css if css else "")
            role = evidence.get(pos)
            detected_date = block.tag == "p" and is_chronology(
                block.element, block.text
            )
            if detected_date:
                assignment = "年代标记（抽取器仅暂存，不导出 Poem）"
            elif role:
                assignment = f"抽取角色：{role[0]}"
                if role[1]:
                    assignment += f"；所在候选词牌：{role[1]}"
            else:
                assignment = "未在当前分册的抽取证据中找到" if collection else "未查询抽取角色（需要 --book）"
            lines.append(
                f"**{'★' if pos == number else '·'} 块 {pos}** "
                f"§{tag}§　{assignment}"
            )
            if block.anchor:
                lines.append(f"    id：§{block.anchor}§")
            text = block.text
            if len(text) > max_chars:
                excerpt = text[:max_chars] + f"……（全文 {len(text)} 字；用 --full 查看）"
            else:
                excerpt = text or "（空）"
            # 使用缩进而不是 Markdown 引用块，便于复制和比较标点与原始来源。
            lines.append("")
            for part in excerpt.splitlines() or [""]:
                lines.append("    " + part)
            lines.append("")
            if show_html:
                lines.extend([
                    "<details><summary>展开原始 XHTML（仅本地）</summary>",
                    "",
                    "§§§html",
                    str(block.element),
                    "§§§",
                    "",
                    "</details>",
                    "",
                ])
        lines.append("---")
        lines.append("")
    return "\n".join(lines).replace("§", "\u0060")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--epub", type=Path, default=Path(
        "data/raw/历代名家词集精华录.epub"
    ), help="本地 EPUB；默认使用数据目录中的词集")
    parser.add_argument("--html", required=True,
                        help="例如 text00264.html")
    parser.add_argument("--block", type=int, action="append", default=[],
                        help="审计报告中的块号，可以重复")
    parser.add_argument("--find", action="append", default=[],
                        help="按原文片段检索当前 XHTML，可以重复")
    parser.add_argument("--book", default="", help="选填：分册名，用来显示抽取角色")
    parser.add_argument("--before", type=int, default=2,
                        help="向前显示几块，默认 2")
    parser.add_argument("--after", type=int, default=4,
                        help="向后显示几块，默认 4")
    parser.add_argument("--max-chars", type=int, default=300,
                        help="长段落的预览字数，默认 300")
    parser.add_argument("--full", action="store_true",
                        help="完整显示上下文中的所有原文")
    parser.add_argument("--show-html", action="store_true",
                        help="附带原始 XHTML，方便检查 span/class/图片")
    parser.add_argument("--output", type=Path,
                        help="可选：保存本地 Markdown；默认直接打印")
    args = parser.parse_args()

    if not args.block and not args.find:
        parser.error("至少指定 --block 2 或 --find 关键词")
    if any(n <= 0 for n in args.block):
        parser.error("--block 必须是正整数")
    book = epub.read_epub(str(args.epub))
    result = inspect_source(
        book, args.html, args.block, find=args.find, collection=args.book,
        before=args.before, after=args.after,
        max_chars=10 ** 9 if args.full else args.max_chars,
        show_html=args.show_html,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result, encoding="utf-8")
        print(f"原始段落查询已保存（包含原书文字，仅供本地查看）：{args.output}")
    else:
        print(result)


if __name__ == "__main__":
    main()
