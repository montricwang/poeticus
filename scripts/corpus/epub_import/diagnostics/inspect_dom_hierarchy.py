"""Inspect raw XHTML containment without publishing copyrighted content.

Unlike the Poem extractor, this diagnostic reports only tag names, class/id
attributes and source-block ordinals. It does NOT infer literary semantics.
"""
import argparse
from pathlib import Path

from bs4 import BeautifulSoup, Tag
from ebooklib import epub

from ..extractor.blocks import iter_source_blocks
from ..extractor.extractor import raw_xhtml


def _signature(tag):
    """Compact, text-free node descriptor and sibling index."""
    if not isinstance(tag, Tag) or tag.name == "[document]":
        return None
    index = 1 + sum(
        isinstance(sibling, Tag) and sibling.name == tag.name
        for sibling in tag.previous_siblings
    )
    classes = "." + ".".join(tag.get("class", [])) if tag.get("class") else ""
    node_id = "#" + tag.get("id") if tag.get("id") else ""
    return f"{tag.name}{node_id}{classes}:nth-of-type({index})"


def _path(tag):
    """Root-to-node DOM path; does not include any inner text."""
    nodes = []
    while isinstance(tag, Tag) and tag.name != "[document]":
        nodes.append(_signature(tag))
        tag = tag.parent
    return " > ".join(reversed(nodes))


def _nearest_common_ancestor(elements):
    """Identity-based LCA: HTML Tags can compare equal by their *contents*."""
    if not elements:
        return None
    first_ancestors = []
    node = elements[0]
    while isinstance(node, Tag) and node.name != "[document]":
        first_ancestors.append(node)
        node = node.parent
    other_ids = []
    for element in elements[1:]:
        ids = set()
        node = element
        while isinstance(node, Tag) and node.name != "[document]":
            ids.add(id(node))
            node = node.parent
        other_ids.append(ids)
    return next(
        (node for node in first_ancestors
         if all(id(node) in ancestors for ancestors in other_ids)),
        None,
    )


def _parse_group(value):
    """Accept a single block number or a closed 1-based ordinal range."""
    parts = value.split("-", 1)
    if len(parts) == 1:
        start = end = int(parts[0])
    else:
        start, end = map(int, parts)
    if not (1 <= start <= end) or end - start > 100:
        raise ValueError(f"Invalid range: {value}")
    return list(range(start, end + 1))


def inspect_hierarchy(book, html_name, groups):
    """Return a text-free structural Markdown report of selected block groups.

    Ordinals follow iter_source_blocks(): h1, h2, h4 and p in document order.
    DOM ancestors are taken from the SAME BeautifulSoup tree as these blocks.
    """
    item = book.get_item_with_href(html_name)
    if item is None:
        raise ValueError(f"EPUB XHTML not found: {html_name}")
    soup = BeautifulSoup(raw_xhtml(item), "lxml")
    by_ordinal = {
        block.ordinal: block for block in iter_source_blocks(soup, html_name)
    }
    lines = [
        "# EPUB DOM 层级审计（只含结构，不含原文）",
        "",
        f"文件：`{html_name}`；块号按 h1/h2/h4/p 出现顺序计数。",
        "",
    ]
    for spec in groups:
        ordinals = _parse_group(spec)
        missing = [n for n in ordinals if n not in by_ordinal]
        if missing:
            raise ValueError(f"{html_name}: block(s) not found: {missing}")
        selected = [by_ordinal[n] for n in ordinals]
        parents = [block.element.parent for block in selected]
        lca = _nearest_common_ancestor([block.element for block in selected])
        same_parent = all(id(p) == id(parents[0]) for p in parents)
        lines.extend([
            f"## 块 {spec}",
            "",
            f"直接父节点相同：{'是' if same_parent else '否'}",
            f"最近共同祖先：`{_path(lca) if lca else '无'}`",
            "",
            "| 块号 | 标签 | class | 直接父节点（完整路径） |",
            "|---:|---|---|---|",
        ])
        for block in selected:
            klass = ", ".join(block.classes) or "—"
            lines.append(
                f"| {block.ordinal} | `{block.tag}` | `{klass}` | "
                f"`{_path(block.element.parent)}` |"
            )
        lines.append("")
    lines.extend([
        "说明：同一父节点只说明 DOM 上是兄弟节点；"
        "最近共同祖先即使是 div/section，也不证明它在文学语义上是评论容器。",
        "",
    ])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--epub", type=Path, default=Path(
        "data/raw/历代名家词集精华录.epub"
    ))
    parser.add_argument("--html", required=True, help="EPUB 内 XHTML 相对路径")
    parser.add_argument(
        "--group", action="append", required=True,
        help="块号或连续区间，如 --group 19-22；可重复"
    )
    parser.add_argument("--output", type=Path,
                        help="可选：输出到本地 Markdown 文件")
    args = parser.parse_args()
    book = epub.read_epub(str(args.epub))
    report = inspect_hierarchy(book, args.html, args.group)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
        print(f"DOM 结构报告：{args.output}")
    else:
        print(report)


if __name__ == "__main__":
    main()
