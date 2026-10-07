from fastapi.testclient import TestClient

from backend.retrieval.server import create_app
from backend.retrieval.serving import (
    ServingCandidate,
    ServingSearchResult,
)


class FakeRuntime:
    startup_profile = {
        "device": "cpu",
        "startup_total_ms": 123.0,
    }

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


def test_retrieval_server_matches_agent_client_contract():
    runtime = FakeRuntime()
    client = TestClient(create_app(runtime))

    response = client.post(
        "/v1/retrieval/search",
        json={
            "text": "片片轻鸥落晚沙",
            "top_k": 8,
            "current": {
                "text": "片片轻鸥落晚沙。",
                "title": "鹧鸪天",
                "author": "陆游",
                "dynasty": "宋",
            },
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "query": "片片轻鸥落晚沙",
        "candidates": [
            {
                "rank": 1,
                "work_id": "dufu-1",
                "text": "片片轻鸥下急湍。",
                "title": "小寒食舟中作",
                "author": "杜甫",
                "dynasty": "唐",
                "source_record_id": "source-1",
                "chronology_status": "clearly_earlier",
                "support_count": 2,
            }
        ],
    }
    assert runtime.calls == [
        {
            "text": "片片轻鸥落晚沙",
            "current_text": "片片轻鸥落晚沙。",
            "current_author": "陆游",
            "target_dynasty": "宋",
            "final_top_k": 8,
        }
    ]


def test_retrieval_server_checks_bearer_token():
    runtime = FakeRuntime()
    client = TestClient(
        create_app(runtime, api_token="secret")
    )

    unauthorized = client.post(
        "/v1/retrieval/search",
        json={
            "text": "甲",
            "current": {"text": "乙"},
        },
    )
    assert unauthorized.status_code == 401

    authorized = client.post(
        "/v1/retrieval/search",
        headers={"Authorization": "Bearer secret"},
        json={
            "text": "甲",
            "current": {"text": "乙"},
        },
    )
    assert authorized.status_code == 200
