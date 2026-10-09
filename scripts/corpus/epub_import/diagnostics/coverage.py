"""核对已解析 XHTML 中的来源块与其他未识别文本。

报告回答结构问题：某个来源块去了哪里？
它不证明字段归类在文学意义上正确，并且只输出来源位置、
标记信息和字符数量。"""
from collections import Counter
from typing import TypedDict

from bs4 import BeautifulSoup, Comment
from bs4.element import NavigableString

from ..extractor.blocks import _class_list, _string_attribute, iter_source_blocks
from ..extractor.extractor import CandidateSection
from ..extractor.extractor import raw_xhtml
from ..extractor.rules import is_chronology, is_non_poem


class BlockSite(TypedDict):
    html: str
    block: int
    tag: str
    classes: list[str]
    anchor: str | None
    text_length: int


class UnsupportedTextSite(TypedDict):
    html: str
    parent_tag: str
    parent_classes: list[str]
    parent_id: str | None
    text_length: int


class CoverageReport(TypedDict):
    total_blocks: int
    handled_blocks: int
    excluded_blocks: int
    untracked_blocks: int
    internal_chronology_not_exported: int
    chronology_sites: list[BlockSite]
    exclusion_types: dict[str, int]
    untracked_sites: list[BlockSite]
    unsupported_text_nodes: int
    unsupported_text_sites: list[UnsupportedTextSite]
    scope: str


EDITORIAL_REGION_PREFIXES = ("导读", "导　读", "总评", "词论")


def source_block_coverage(
    book, files: list[str], sections: list[CandidateSection], collection: str,
) -> CoverageReport:
    """只审计实际处理过的 XHTML，不把它冒充为整本 EPUB 的完整覆盖。

    handled：来源块已进入抽取器的中间证据。
    excluded：结构性 h1 或已知的编校区域/非作品标题。
    internal_chronology_not_exported：从纪年段落推断了内部元数据，
        但最终 Poem Schema 没有承载，不能计入已导出。
    untracked：既未处理，也未明确排除的段落或标题。

    位置由 XHTML 文件名和顺序块号组成。每个来源段落仅对应一种状态，
    报告不包含原文。
    """
    evidence = {
        (section["html"], block["block"])
        for section in sections
        for block in section["blocks"]
    }
    counters = Counter()
    untracked: list[BlockSite] = []
    chronology_sites: list[BlockSite] = []
    unsupported_text: list[UnsupportedTextSite] = []

    for filename in files:
        item = book.get_item_with_href(filename)
        if item is None:
            raise ValueError(f"EPUB XHTML not found: {filename}")
        soup = BeautifulSoup(raw_xhtml(item), "lxml")
        editorial_region = False
        editorial_section = False
        for block in iter_source_blocks(soup, filename):
            key = (filename, block.ordinal)
            if block.tag == "h1":
                editorial_region = block.text.startswith(EDITORIAL_REGION_PREFIXES)
                editorial_section = False
            is_editorial_heading = (
                block.tag == "h2" and is_non_poem(collection, block.text)
            )
            if block.tag == "h2":
                editorial_section = is_editorial_heading
            # 年代标签会被识别为后续作品的上下文，但 convert_to_poem
            # 有意不发布 section.chronology。即便相邻作品已有 block evidence，
            # 也要把这类元数据缺失明确暴露出来，不能误判为已经完整导出。
            if block.tag == "p" and is_chronology(block.element, block.text):
                status = "internal_chronology_not_exported"
            elif key in evidence:
                status = "handled"
            elif block.tag == "h1":
                status = "excluded_structural_heading"
            elif editorial_region:
                status = "excluded_editorial_region"
            elif editorial_section:
                status = "excluded_editorial_heading"
            else:
                status = "untracked"
            counters[status] += 1
            if status == "untracked":
                untracked.append({
                    "html": filename, "block": block.ordinal,
                    "tag": block.tag, "classes": list(block.classes),
                    "anchor": block.anchor, "text_length": len(block.text),
                })
            elif status == "internal_chronology_not_exported":
                chronology_sites.append({
                    "html": filename, "block": block.ordinal,
                    "tag": block.tag, "classes": list(block.classes),
                    "anchor": block.anchor, "text_length": len(block.text),
                })
        # iter_source_blocks 有意只扫描 h1/h2/h4/p。所有这些标签之外的文本
        # 要单独盘点，否则 div、li 或 body 直接文本可能悄悄消失而没有 coverage warning。
        body = soup.body or soup
        for text_node in body.descendants:
            if (not isinstance(text_node, NavigableString)
                    or isinstance(text_node, Comment)
                    or not str(text_node).strip()):
                continue
            ancestry = list(text_node.parents)
            if any(parent.name in {"h1", "h2", "h4", "p",
                                   "script", "style", "noscript", "svg"}
                   for parent in ancestry):
                continue
            parent = text_node.parent
            unsupported_text.append({
                "html": filename,
                "parent_tag": parent.name if parent else "unknown",
                "parent_classes": _class_list(parent) if parent else [],
                "parent_id": _string_attribute(parent, "id") if parent else None,
                "text_length": len(str(text_node).strip()),
            })

    total = sum(counters.values())
    excluded = sum(n for label, n in counters.items()
                   if label.startswith("excluded_"))
    report: CoverageReport = {
        "total_blocks": total,
        "handled_blocks": counters["handled"],
        "excluded_blocks": excluded,
        "untracked_blocks": len(untracked),
        "internal_chronology_not_exported": len(chronology_sites),
        "chronology_sites": chronology_sites,
        "exclusion_types": {
            label: count for label, count in sorted(counters.items())
            if label.startswith("excluded_")
        },
        "untracked_sites": untracked,
        "unsupported_text_nodes": len(unsupported_text),
        "unsupported_text_sites": unsupported_text,
        "scope": (
            "XHTML selected by collection TOC; tracked tags are h1/h2/h4/p, "
            "other non-whitespace text nodes inventoried separately; "
            "not every XHTML file in EPUB"
        ),
    }
    return report
