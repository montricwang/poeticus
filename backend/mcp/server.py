from typing import Literal

from mcp.server import MCPServer

from backend.evidence.providers.cnkgraph import CNKGraphProvider
from backend.evidence.service import EvidenceService


mcp = MCPServer("Poeticus")

evidence_service = EvidenceService(
    {
        "cnkgraph": CNKGraphProvider(),
    }
)


async def _search(
    query: str,
    evidence_type: Literal["allusion", "reference"],
    limit: int,
) -> dict[str, object]:
    query = query.strip()

    if not query or len(query) > 120:
        raise ValueError("查询内容必须为 1 至 120 个字符")

    items = await evidence_service.search(
        query,
        provider_name="cnkgraph",
        evidence_type=evidence_type,
    )

    evidences = [
        {**item.model_dump(), "text": item.text[:1600]} for item in items[:limit]
    ]

    return {
        "status": "ok" if evidences else "no_hit",
        "query": query,
        "evidence_type": evidence_type,
        "evidences": evidences,
    }


@mcp.tool()
async def lookup_allusion(term: str) -> dict[str, object]:
    """查询古典诗词中的人物故事、掌故与神话典故。"""
    return await _search(term, "allusion", limit=3)


@mcp.tool()
async def lookup_reference(text: str) -> dict[str, object]:
    """查询诗句可能对应的前代诗文或化用候选；结果不代表已证实引用。"""
    return await _search(text, "reference", limit=5)


if __name__ == "__main__":
    mcp.run()
