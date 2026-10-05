"""EPUB 导入中间结构，与前端 Poem JSON 明确分离。"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class PoemContent:
    text: List[str] = field(default_factory=list)
    prefaces: List[str] = field(default_factory=list)
    annotations: List[str] = field(default_factory=list)
    commentaries: List[str] = field(default_factory=list)
    # 仅抽取层使用：记录带来源位置的行内注记；正文仍保留原始文本。
    inline_notes: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class Poem:
    id: str
    author: str
    cipai: Optional[str]
    title: Optional[str]
    content: PoemContent
    collection: str
    source: str = ""
    # 贺铸自拟的寓声题头既不是原词牌，也不是作品词题。
    yusheng_title: Optional[str] = None
    warnings: List[Dict[str, Any]] = field(default_factory=list)
