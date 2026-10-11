"""验证 MCP 工具发现、调用及错误处理，不访问外部网络。"""

import asyncio

import pytest
from mcp import Client

from backend.evidence.providers.cnkgraph import CNKGraphError
from backend.evidence.schema import EvidenceItem
from backend.evidence.service import EvidenceService
from backend.mcp import server


class FakeProvider:
    async def search(
        self,
        query: str,
        evidence_type: str | None = None,
    ) -> list[EvidenceItem]:
        if query == "接口故障":
            raise CNKGraphError("模拟 HTTP 503")

        if query == "不存在":
            return []

        assert evidence_type in ("allusion", "reference")
        return [
            EvidenceItem(
                anchor=query,
                type=evidence_type,
                text="模拟查询结果",
                provider="fake",
                status="candidate",
            )
        ]


@pytest.fixture(autouse=True)
def mock_evidence_service(monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setattr(
        server,
        "evidence_service",
        EvidenceService({"cnkgraph": FakeProvider()}),
    )


def test_mcp_tools():
    async def check():
        async with Client(server.mcp) as client:
            tools = await client.list_tools()
            assert {tool.name for tool in tools.tools} == {
                "lookup_allusion",
                "lookup_reference",
            }

            for name, arguments, expected_type in [
                ("lookup_allusion", {"term": "刘郎"}, "allusion"),
                ("lookup_reference", {"text": "大江东去"}, "reference"),
            ]:
                result = await client.call_tool(name, arguments)

                assert not result.is_error
                data = result.structured_content
                assert data is not None
                assert data["status"] == "ok"
                assert data["evidence_type"] == expected_type
                assert len(data["evidences"]) == 1

            result = await client.call_tool(
                "lookup_allusion",
                {"term": "不存在"},
            )
            assert not result.is_error
            assert result.structured_content["status"] == "no_hit"
            assert result.structured_content["evidences"] == []

    asyncio.run(check())


def test_mcp_rejects_invalid_input():
    async def check():
        async with Client(server.mcp) as client:
            for term in ["", " " * 3, "刘" * 121]:
                result = await client.call_tool(
                    "lookup_allusion",
                    {"term": term},
                )
                assert result.is_error

    asyncio.run(check())


def test_mcp_reports_provider_failure():
    async def check():
        async with Client(server.mcp) as client:
            result = await client.call_tool(
                "lookup_reference",
                {"text": "接口故障"},
            )
            assert result.is_error

    asyncio.run(check())
