"""EPUB 导入中间结构，与前端 Poem JSON 明确分离。"""
from dataclasses import dataclass, field
from typing import TypedDict


class InlineNoteCandidate(TypedDict):
    """A reversible font1 span record; positions refer to the flattened verse."""

    kind: str
    origin: str
    source_html: str
    source_block: int
    paragraph_index: int
    start: int
    end: int
    text: str
    span_class: str
    boundary: str
    punctuation_outside_span: bool
    body_retains_note: bool


@dataclass
class PoemContent:
    text: list[str] = field(default_factory=list)
    prefaces: list[str] = field(default_factory=list)
    annotations: list[str] = field(default_factory=list)
    commentaries: list[str] = field(default_factory=list)
    # 仅抽取层使用：记录带来源位置的行内注记；正文仍保留原始文本。
    inline_notes: list[InlineNoteCandidate] = field(default_factory=list)


@dataclass
class Poem:
    id: str
    author: str
    cipai: str | None
    title: str | None
    content: PoemContent
    collection: str
    source: str = ""
    # 贺铸自拟的寓声题头既不是原词牌，也不是作品词题。
    yusheng_title: str | None = None
    warnings: list[dict[str, object]] = field(default_factory=list)
