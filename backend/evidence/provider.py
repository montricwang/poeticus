from typing import Protocol

from .schema import EvidenceItem


class EvidenceProvider(Protocol):
    """
    Evidence 数据来源接口。

    任何外部知识源都需要实现这个接口。
    例如：
    - CNKGraph
    - RAG
    - Dictionary API
    """

    async def search(
        self,
        query: str,
        evidence_type: str | None = None,
    ) -> list[EvidenceItem]: ...
