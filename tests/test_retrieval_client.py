import asyncio
import json

import httpx
import pytest

from backend.retrieval.client import (
    CurrentPoem,
    RetrievalClientError,
    TextRetrievalClient,
)


def test_retrieval_client_posts_query_and_current_poem_context():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["authorization"] = request.headers.get("Authorization")
        seen["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "status": "ok",
                "query": "片片轻鸥落晚沙",
                "candidates": [
                    {
                        "rank": 1,
                        "work_id": "dufu-1",
                        "title": "小寒食舟中作",
                        "author": "杜甫",
                        "dynasty": "唐",
                        "text": "片片轻鸥下急湍。",
                        "chronology_status": "clearly_earlier",
                        "support_count": 2,
                    }
                ],
            },
        )

    client = TextRetrievalClient(
        base_url="https://retrieval.example",
        api_token="secret",
        transport=httpx.MockTransport(handler),
    )

    result = asyncio.run(
        client.search(
            text="片片轻鸥落晚沙",
            current_poem=CurrentPoem(
                text="片片轻鸥落晚沙。",
                title="鹧鸪天",
                author="陆游",
                dynasty="宋",
            ),
            top_k=8,
        )
    )

    assert seen["path"] == "/v1/retrieval/search"
    assert seen["authorization"] == "Bearer secret"
    assert seen["payload"] == {
        "text": "片片轻鸥落晚沙",
        "top_k": 8,
        "current": {
            "text": "片片轻鸥落晚沙。",
            "title": "鹧鸪天",
            "author": "陆游",
            "dynasty": "宋",
        },
    }
    assert result.status == "ok"
    assert result.candidates[0].author == "杜甫"


def test_retrieval_client_rejects_malformed_candidate_ranks():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status": "ok",
                "query": "甲",
                "candidates": [
                    {
                        "rank": 2,
                        "work_id": "w",
                        "text": "乙",
                    }
                ],
            },
        )

    client = TextRetrievalClient(
        base_url="https://retrieval.example",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(RetrievalClientError, match="rank 不连续"):
        asyncio.run(
            client.search(
                text="甲",
                current_poem=CurrentPoem(text="甲"),
            )
        )


def test_retrieval_client_requires_configured_service():
    client = TextRetrievalClient(base_url="")

    with pytest.raises(RetrievalClientError, match="尚未配置"):
        asyncio.run(
            client.search(
                text="甲",
                current_poem=CurrentPoem(text="甲"),
            )
        )
