import sys

import pytest
from fastapi.testclient import TestClient

from backend.retrieval.poem.server import create_app
from backend.retrieval.poem.serving import (
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
    client = TestClient(create_app(runtime, api_token="secret"))

    response = client.post(
        "/v1/retrieval/search",
        headers={"Authorization": "Bearer secret"},
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

    incorrect = client.post(
        "/v1/retrieval/search",
        headers={"Authorization": "Bearer incorrect"},
        json={"text": "甲", "current": {"text": "乙"}},
    )
    assert incorrect.status_code == 401
    assert client.get("/v1/retrieval/profile").status_code == 401
    assert client.get(
        "/v1/retrieval/profile",
        headers={"Authorization": "Bearer secret"},
    ).status_code == 200
    assert client.get("/health").status_code == 200
    assert runtime.calls == []

    authorized = client.post(
        "/v1/retrieval/search",
        headers={"Authorization": "Bearer secret"},
        json={
            "text": "甲",
            "current": {"text": "乙"},
        },
    )
    assert authorized.status_code == 200

    assert runtime.calls == [
        {
            "text": "甲",
            "current_text": "乙",
            "current_author": None,
            "target_dynasty": None,
            "final_top_k": 8,
        }
    ]


@pytest.mark.parametrize("token", ["", " ", "\t"])
def test_retrieval_server_rejects_empty_token(token):
    with pytest.raises(ValueError, match="Token 不能为空"):
        create_app(FakeRuntime(), api_token=token)


@pytest.mark.parametrize(
    ("env_token", "cli_args"),
    [
        ("", []),
        ("   ", []),
        ("secret", ["--api-token", " "]),
    ],
)
def test_retrieval_serving_cli_rejects_empty_token_before_loading_indices(
    monkeypatch, capsys, env_token, cli_args
):
    from scripts.retrieval import run_serving

    monkeypatch.setenv("POETICUS_RETRIEVAL_TOKEN", env_token)
    monkeypatch.setattr(sys, "argv", ["run_serving", *cli_args])

    with pytest.raises(SystemExit) as error:
        run_serving.main()

    assert error.value.code == 2
    assert "POETICUS_RETRIEVAL_TOKEN" in capsys.readouterr().err
