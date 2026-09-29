"""测试 CNKGraph 证据检索：成功、空结果与外部服务异常。"""

import asyncio
import json
from urllib.parse import unquote

import httpx
import pytest

from backend.evidence.providers.cnkgraph import CNKGraphError, CNKGraphProvider
from backend.evidence.service import EvidenceService


@pytest.fixture(autouse=True)
def no_tracing(monkeypatch):
    """禁用 LangSmith 上报，测试期间不允许网络请求。"""

    monkeypatch.setenv("LANGSMITH_TRACING", "false")


@pytest.fixture
def evidence_service():
    return EvidenceService({"cnkgraph": CNKGraphProvider()})


@pytest.fixture
def mock_cnkgraph_http(monkeypatch):
    """替换 CNKGraph 使用的 HTTP 客户端，禁止真实网络请求。"""

    real_async_client = httpx.AsyncClient

    def install(handler):
        def make_client(**kwargs):
            return real_async_client(
                transport=httpx.MockTransport(handler),
                **kwargs,
            )

        monkeypatch.setattr(
            httpx,
            "AsyncClient",
            make_client,
        )

    return install


def _search(evidence_service, query="刘郎"):
    return asyncio.run(
        evidence_service.search(
            query=query,
            provider_name="cnkgraph",
            evidence_type="allusion",
        )
    )


def test_evidence_success(evidence_service, mock_cnkgraph_http):
    """HTTP 200：正确解析候选证据及来源。"""

    def handler(request: httpx.Request):
        assert request.method == "POST"
        assert unquote(request.url.path) == ("/api/glossary/典故/find")
        assert json.loads(request.content) == {
            "key": "刘郎",
            "charIndex": "end",
        }

        return httpx.Response(
            200,
            json=[
                {
                    "Explains": [
                        {
                            "Key": "刘郎",
                            "Explain": "刘晨入天台遇仙。",
                        }
                    ],
                    "Quotes": [
                        {
                            "Content": "刘晨、阮肇入天台采药。",
                            "Book": "《太平广记》",
                        }
                    ],
                }
            ],
        )

    mock_cnkgraph_http(handler)

    results = _search(evidence_service)

    assert len(results) == 1

    evidence = results[0]
    assert evidence.anchor == "刘郎"
    assert evidence.type == "allusion"
    assert evidence.provider == "cnkgraph"
    assert evidence.status == "candidate"
    assert evidence.source is not None
    assert evidence.source.title == "《太平广记》"
    assert "刘晨入天台" in evidence.text
    assert "刘晨、阮肇" in evidence.text


def test_evidence_not_found(evidence_service, mock_cnkgraph_http):
    """HTTP 404：视为典故查询无结果，返回空列表。"""

    def handler(request: httpx.Request):
        return httpx.Response(
            404,
            json={"Message": "未找到相关结果"},
        )

    mock_cnkgraph_http(handler)

    assert _search(evidence_service, query="绸缪") == []


def test_evidence_provider_error(evidence_service, mock_cnkgraph_http):
    """HTTP 503：区分服务故障与没有检索结果。"""

    def handler(request: httpx.Request):
        return httpx.Response(
            503,
            json={"Message": "Service Unavailable"},
        )

    mock_cnkgraph_http(handler)

    with pytest.raises(CNKGraphError, match="HTTP 503"):
        _search(evidence_service, query="绸缪")
