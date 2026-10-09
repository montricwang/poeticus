from typing import Literal
from pydantic import BaseModel


class EvidenceSource(BaseModel):
    title: str | None = None
    author: str | None = None
    work: str | None = None
    url: str | None = None


class EvidenceItem(BaseModel):
    anchor: str

    type: Literal[
        "allusion",
        "dictionary",
        "reference",
        "commentary",
    ]

    text: str

    source: EvidenceSource | None = None

    provider: str

    status: Literal[
        "verified",
        "candidate",
        "not_found",
        "error",
    ]

    metadata: dict[str, object] = {}
