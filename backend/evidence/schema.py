"""证据服务的统一数据模型，描述证据内容和出处。"""

from typing import Literal
from pydantic import BaseModel


class EvidenceSource(BaseModel):
    """记录证据的作品、作者及可用的来源链接。"""

    title: str | None = None
    author: str | None = None
    work: str | None = None
    url: str | None = None


class EvidenceItem(BaseModel):
    """一条标准化证据：内容、类型、来源、提供者和核实状态。"""

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
