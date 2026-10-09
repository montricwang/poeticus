"""Shared EPUB glyph source ordering and image loading.

This module must not import review entrypoints; both the review sheet and
the private context renderer use it to avoid a circular import.
"""
import posixpath
from typing import TypedDict


class GlyphSite(TypedDict):
    slug: str
    src: str
    collection: str
    pages: list[str]


def glyph_sites(report) -> list[GlyphSite]:
    """Keep a single review row per (collection slug, image source)."""
    cases: dict[tuple[str, str], GlyphSite] = {}
    for collection in report["collections"]:
        for site in collection["missing_glyphs"]:
            slug, src, page = collection["slug"], site["src"], site["html"]
            key = (slug, src)
            if key not in cases:
                cases[key] = {
                    "slug": slug,
                    "src": src,
                    "collection": collection["collection"],
                    "pages": [],
                }
            if page not in cases[key]["pages"]:
                cases[key]["pages"].append(page)
    return list(cases.values())


def _epub_image(book, page: str, src: str) -> bytes | None:
    """Resolve only images inside the EPUB's relative source tree."""
    if "://" in src or src.startswith("/"):
        raise ValueError(f"EPUB 图片路径异常：{src}")
    href = posixpath.normpath(posixpath.join(posixpath.dirname(page), src))
    if href.startswith("../"):
        raise ValueError(f"EPUB 图片路径越界：{page} / {src}")
    item = book.get_item_with_href(href)
    if item is None:
        return None
    return item.get_content() if hasattr(item, "get_content") else item.content
