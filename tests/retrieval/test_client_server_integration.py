import asyncio

import httpx

from backend.retrieval.client import CurrentPoem, TextRetrievalClient
from backend.retrieval.server import create_app
from backend.retrieval.serving import ServingCandidate, ServingSearchResult


class FakeRuntime:
    startup_profile = {"device": "cpu"}

    def __init__(self):
        self.calls = []

    def search(
        self,
        text,
        *,
        current_text,
        current_author,
        target_dynasty,
        final_top_k,
    ):
        self.calls.append(
            {
                "text": text,
                "current_text": current_text,
                "current_author": current_author,
                "target_dynasty": target_dynasty,
                "final_top_k": final_top_k,
            }
        )
        return ServingSearchResult(
            status="ok",
            query=text,
            candidates=(
                ServingCandidate(
                    rank=1,
                    work_id="dufu-1",
                    text="片片轻鸥下急湍。",
                    title="小寒食舟中作",
                    author="杜甫",
                    dynasty="唐",
                    source_record_id="source-1",
                    chronology_status="clearly_earlier",
                    support_count=2,
                ),
            ),
            current_work_aliases=("luyou-1",),
            timings_ms={"total_ms": 10.0},
        )


def test_http_client_and_serving_api_contract_end_to_end():
    runtime = FakeRuntime()
    app = create_app(runtime, api_token="secret")
    transport = httpx.ASGITransport(app=app)
    client = TextRetrievalClient(
        base_url="http://retrieval.local",
        api_token="secret",
        transport=transport,
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

    assert result.status == "ok"
    assert result.candidates[0].author == "杜甫"
    assert result.candidates[0].text == "片片轻鸥下急湍。"
    assert runtime.calls == [
        {
            "text": "片片轻鸥落晚沙",
            "current_text": "片片轻鸥落晚沙。",
            "current_author": "陆游",
            "target_dynasty": "宋",
            "final_top_k": 8,
        }
    ]
