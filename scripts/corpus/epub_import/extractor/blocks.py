"""Lossless-enough block evidence for EPUB semantic extraction.

Keep source locations, immediate inline nodes and structural boundaries before
assigning literary roles. This representation is local to the extraction stage.
"""
from dataclasses import dataclass, field

from bs4 import NavigableString, Tag


@dataclass
class SourceBlock:
    html: str
    ordinal: int
    tag: str
    classes: tuple
    anchor: str | None
    text: str
    runs: list[dict]
    element: Tag = field(repr=False, compare=False)

    def location(self) -> dict:
        return {"html": self.html, "block": self.ordinal, "tag": self.tag,
                "classes": list(self.classes), "anchor": self.anchor}


def inline_runs(element: Tag) -> list[dict]:
    """Record direct parts rather than flattening a composite title."""
    result = []
    for child in element.children:
        if isinstance(child, NavigableString):
            if str(child).strip():
                result.append({"tag": "text", "text": str(child)})
        elif isinstance(child, Tag):
            if child.name == "br":
                result.append({"tag": "br", "text": "\n"})
            elif child.name == "img":
                result.append({"tag": "img", "src": child.get("src", "")})
            else:
                result.append({"tag": child.name, "classes": child.get("class", []),
                               "style": child.get("style", ""),
                               "text": child.get_text("", strip=True)})
    return result


def iter_source_blocks(soup: Tag, html_name: str):
    """Yield ordered paragraph/heading blocks; never assign semantic roles."""
    body = soup.body or soup
    for ordinal, tag in enumerate(body.find_all(["h1", "h2", "h4", "p"]), 1):
        yield SourceBlock(
            html=html_name, ordinal=ordinal, tag=tag.name,
            classes=tuple(tag.get("class", [])), anchor=tag.get("id"),
            text=tag.get_text("", strip=True), runs=inline_runs(tag), element=tag,
        )
