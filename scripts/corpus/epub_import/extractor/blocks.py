"""为 EPUB 语义抽取保留尽量无损的块级证据。

先保存来源位置、直接行内节点和结构边界，再判断它们的文学角色。
这个中间结构只在抽取阶段使用。"""
from dataclasses import dataclass, field
from collections.abc import Iterator
from typing import NotRequired, TypedDict

from bs4 import Tag
from bs4.element import NavigableString


class InlineRun(TypedDict):
    tag: str
    text: NotRequired[str]
    src: NotRequired[str]
    classes: NotRequired[list[str]]
    style: NotRequired[str]


def _string_attribute(element: Tag, key: str) -> str | None:
    value = element.get(key)
    return value if isinstance(value, str) else None


def _class_list(element: Tag) -> list[str]:
    value = element.get("class")
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    if isinstance(value, str):
        return value.split()
    return []


@dataclass
class SourceBlock:
    html: str
    ordinal: int
    tag: str
    classes: tuple[str, ...]
    anchor: str | None
    text: str
    runs: list[InlineRun]
    element: Tag = field(repr=False, compare=False)

    def location(self) -> dict[str, object]:
        return {"html": self.html, "block": self.ordinal, "tag": self.tag,
                "classes": list(self.classes), "anchor": self.anchor}


def inline_runs(element: Tag) -> list[InlineRun]:
    """记录直接组成部分，不把复合标题提前拍平成字符串。"""
    result: list[InlineRun] = []
    for child in element.children:
        if isinstance(child, NavigableString):
            if str(child).strip():
                result.append({"tag": "text", "text": str(child)})
        elif isinstance(child, Tag):
            if child.name == "br":
                result.append({"tag": "br", "text": "\n"})
            elif child.name == "img":
                result.append({"tag": "img", "src": _string_attribute(child, "src") or ""})
            else:
                result.append({"tag": child.name or "", "classes": _class_list(child),
                               "style": _string_attribute(child, "style") or "",
                               "text": child.get_text("", strip=True)})
    return result


def iter_source_blocks(soup: Tag, html_name: str) -> Iterator[SourceBlock]:
    """按顺序产出段落与标题块，本层不分配语义角色。"""
    body = soup.body or soup
    for ordinal, tag in enumerate(body.find_all(["h1", "h2", "h4", "p"]), 1):
        yield SourceBlock(
            html=html_name, ordinal=ordinal, tag=tag.name or "",
            classes=tuple(_class_list(tag)), anchor=_string_attribute(tag, "id"),
            text=tag.get_text("", strip=True), runs=inline_runs(tag), element=tag,
        )
