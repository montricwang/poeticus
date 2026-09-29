"""测试 Evidence 查询成功、空结果与外部服务异常。"""

import json
from urllib.parse import unquote

import httpx
import pytest

from poem_context import PoemContext

SAMPLE_CONTEXT = PoemContext(
    id="test-poem",
    title="测试",
    author="苏轼",
    dynasty="宋",
    review_status="imported_unreviewed",
)


@pytest.fixture
def router(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-only-placeholder")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")

    import intent_router

    return intent_router


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


def test_evidence_success(
    monkeypatch,
    router,
    mock_cnkgraph_http,
):
    """HTTP 200：获取典故、转换证据，并交给 LLM 回答。"""

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

    answer_calls = []

    def fake_answer(**kwargs):
        answer_calls.append(kwargs)
        return "候选证据记载了刘晨入天台的故事。"

    monkeypatch.setattr(
        router,
        "answer_with_evidence",
        fake_answer,
    )

    result = router.source_lookup(
        {
            "poem": "测试诗歌",
            "question": "「刘郎」有什么典故？",
            "selection": None,
            "context": SAMPLE_CONTEXT,
        }
    )

    assert result["next_step"] == "source_lookup"
    assert result["reply"] == ("候选证据记载了刘晨入天台的故事。")

    assert len(result["evidences"]) == 1

    evidence = result["evidences"][0]
    assert evidence["anchor"] == "刘郎"
    assert evidence["type"] == "allusion"
    assert evidence["provider"] == "cnkgraph"
    assert evidence["status"] == "candidate"
    assert evidence["source"]["title"] == "《太平广记》"
    assert "刘晨入天台" in evidence["text"]
    assert "刘晨、阮肇" in evidence["text"]

    assert len(answer_calls) == 1
    assert answer_calls[0]["question"] == ("「刘郎」有什么典故？")
    assert answer_calls[0]["context"] == SAMPLE_CONTEXT
    assert len(answer_calls[0]["evidences"]) == 1


def test_evidence_not_found(
    monkeypatch,
    router,
    mock_cnkgraph_http,
):
    """HTTP 404：视为典故查询无结果，不调用 LLM。"""

    def handler(request: httpx.Request):
        return httpx.Response(
            404,
            json={"Message": "未找到相关结果"},
        )

    mock_cnkgraph_http(handler)

    def forbidden_answer(**kwargs):
        pytest.fail("没有证据时不应该调用 LLM")

    monkeypatch.setattr(
        router,
        "answer_with_evidence",
        forbidden_answer,
    )

    result = router.source_lookup(
        {
            "poem": "三星当户照绸缪。",
            "question": "这个词出自哪里？",
            "selection": "绸缪",
            "context": SAMPLE_CONTEXT,
        }
    )

    assert result["next_step"] == "source_lookup"
    assert result["evidences"] == []
    assert "没有检索到" in result["reply"]
    assert "绸缪" in result["reply"]
    assert "不代表" in result["reply"]


def test_evidence_provider_error(
    monkeypatch,
    router,
    mock_cnkgraph_http,
):
    """HTTP 503：区分服务故障与没有检索结果。"""

    def handler(request: httpx.Request):
        return httpx.Response(
            503,
            json={"Message": "Service Unavailable"},
        )

    mock_cnkgraph_http(handler)

    def forbidden_answer(**kwargs):
        pytest.fail("检索失败时不应该调用 LLM")

    monkeypatch.setattr(
        router,
        "answer_with_evidence",
        forbidden_answer,
    )

    result = router.source_lookup(
        {
            "poem": "三星当户照绸缪。",
            "question": "这个词出自哪里？",
            "selection": "绸缪",
            "context": SAMPLE_CONTEXT,
        }
    )

    assert result["next_step"] == "source_lookup"
    assert "查询失败" in result["reply"]
    assert "未能取得证据" in result["reply"]
