"""Account for every top-level source block in parsed XHTML documents.

This report answers a structural question: where did a source block go?
It does not assert that a field assignment is semantically correct.
It intentionally exposes only locations, markup and character counts.
"""
from collections import Counter

from bs4 import BeautifulSoup

from ..extractor.blocks import iter_source_blocks
from ..extractor.extractor import raw_xhtml
from ..extractor.rules import is_non_poem


EDITORIAL_REGION_PREFIXES = ("导读", "导　读", "总评", "词论")


def source_block_coverage(book, files, sections, collection):
    """Audit processed XHTML only; do not silently claim EPUB-wide coverage.

    handled: source block appears in the extractor's intermediate evidence.
    excluded: a structural h1 or known editorial region/non-poem heading.
    untracked: paragraph/heading neither handled nor explicitly excluded.

    Positions use (XHTML filename, ordinal). A source paragraph contributes
    exactly one status, and no source text is included in the report.
    """
    evidence = {
        (section["html"], block["block"])
        for section in sections
        for block in section["blocks"]
    }
    counters = Counter()
    untracked = []

    for filename in files:
        item = book.get_item_with_href(filename)
        if item is None:
            raise ValueError(f"EPUB XHTML not found: {filename}")
        soup = BeautifulSoup(raw_xhtml(item), "lxml")
        editorial_region = False
        for block in iter_source_blocks(soup, filename):
            key = (filename, block.ordinal)
            if block.tag == "h1":
                editorial_region = block.text.startswith(EDITORIAL_REGION_PREFIXES)
            is_editorial_heading = (
                block.tag == "h2" and is_non_poem(collection, block.text)
            )
            if key in evidence:
                status = "handled"
            elif block.tag == "h1":
                status = "excluded_structural_heading"
            elif editorial_region:
                status = "excluded_editorial_region"
            elif is_editorial_heading:
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

    total = sum(counters.values())
    excluded = sum(n for label, n in counters.items()
                   if label.startswith("excluded_"))
    return {
        "total_blocks": total,
        "handled_blocks": counters["handled"],
        "excluded_blocks": excluded,
        "untracked_blocks": len(untracked),
        "exclusion_types": {
            label: count for label, count in sorted(counters.items())
            if label.startswith("excluded_")
        },
        "untracked_sites": untracked,
        "scope": "XHTML selected by the collection TOC; not every file in EPUB",
    }
