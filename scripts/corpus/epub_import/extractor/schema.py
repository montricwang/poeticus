"""Intermediate EPUB import schema, distinct from the frontend Poem JSON."""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class PoemContent:
    text: List[str] = field(default_factory=list)
    prefaces: List[str] = field(default_factory=list)
    annotations: List[str] = field(default_factory=list)
    commentaries: List[str] = field(default_factory=list)
    # Extractor-only: source-positioned inline notes; verse retains raw text.
    inline_notes: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class Poem:
    id: str
    author: str
    tune: Optional[str]
    title: Optional[str]
    content: PoemContent
    collection: str
    source: str = ""
    # He Zhu's author-coined tune heading, distinct from tune and poem title.
    yusheng: Optional[str] = None
    warnings: List[Dict[str, Any]] = field(default_factory=list)
