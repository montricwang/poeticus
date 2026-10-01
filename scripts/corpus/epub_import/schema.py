from dataclasses import dataclass, field
from typing import List


@dataclass
class PoemContent:
    text: List[str] = field(default_factory=list)
    annotations: List[str] = field(default_factory=list)
    commentaries: List[str] = field(default_factory=list)


@dataclass
class Poem:
    id: str
    author: str
    title_raw: str
    content: PoemContent
    collection: str
    source: str = ""
