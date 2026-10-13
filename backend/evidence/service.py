"""证据服务：校验查询请求，并将请求交给指定的证据来源。"""

from .provider import EvidenceProvider
from .schema import EvidenceItem


class EvidenceService:
    """保存已注册的 Provider，按名称选择证据来源。"""

    def __init__(self, providers: dict[str, EvidenceProvider]):
        """接收 Provider 名称到实例的映射。"""

        self.providers = providers

    async def search(
        self,
        query: str,
        *,
        provider_name: str,
        evidence_type: str | None = None,
    ) -> list[EvidenceItem]:
        """校验查询内容与来源名称，返回指定 Provider 的查询结果。"""

        query = query.strip()
        if not query:
            raise ValueError("查询内容不能为空")

        provider = self.providers.get(provider_name)
        if provider is None:
            raise ValueError(f"未注册的证据来源：{provider_name}")

        return await provider.search(query, evidence_type)
