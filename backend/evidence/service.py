from .provider import EvidenceProvider
from .schema import EvidenceItem


class EvidenceService:
    def __init__(self, providers: dict[str, EvidenceProvider]):
        self.providers = providers

    async def search(
        self,
        query: str,
        *,
        provider_name: str,
        evidence_type: str | None = None,
    ) -> list[EvidenceItem]:
        query = query.strip()
        if not query:
            raise ValueError("查询内容不能为空")

        provider = self.providers.get(provider_name)
        if provider is None:
            raise ValueError(f"未注册的证据来源：{provider_name}")

        return await provider.search(query, evidence_type)
