"""证据来源的共同查询接口，供 EvidenceService 按统一方式使用。"""

from typing import Protocol

from .schema import EvidenceItem


class EvidenceProvider(Protocol):
    """规定证据来源的异步查询方法及统一返回类型。"""

    async def search(
        self,
        query: str,
        evidence_type: str | None = None,
    ) -> list[EvidenceItem]: ...
