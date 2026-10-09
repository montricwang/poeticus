"""共用的 EPUB 图片字来源顺序和图像加载规则。

不能在此模块导入人工复核入口；复核图版和私人上下文渲染器
共用这里的函数，以避免循环依赖。"""
import posixpath
from typing import TypedDict


class GlyphSite(TypedDict):
    slug: str
    src: str
    collection: str
    pages: list[str]


def glyph_sites(report) -> list[GlyphSite]:
    """每组（分册 slug、图片来源）只保留一条复核记录。"""
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
    """只定位 EPUB 相对来源目录内的图片，拒绝越界引用。"""
    if "://" in src or src.startswith("/"):
        raise ValueError(f"EPUB 图片路径异常：{src}")
    href = posixpath.normpath(posixpath.join(posixpath.dirname(page), src))
    if href.startswith("../"):
        raise ValueError(f"EPUB 图片路径越界：{page} / {src}")
    item = book.get_item_with_href(href)
    if item is None:
        return None
    return item.get_content() if hasattr(item, "get_content") else item.content
