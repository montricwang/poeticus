"""CNKGraph provider 的窄证据映射测试，不访问真实网络。"""

import asyncio

from backend.evidence.providers.cnkgraph import CNKGraphProvider


def test_reference_response_maps_to_evidence_items(monkeypatch):
    provider = CNKGraphProvider()

    async def fake_request_json(path, payload):
        assert path == "/api/tool/reference"
        assert payload == {"content": "片片轻鸥落晚沙"}
        return {
            "Sentences": [
                {
                    "Clause": "片片轻鸥落晚沙",
                    "References": [
                        {
                            "WritingId": 30573,
                            "Dynasty": "唐",
                            "Author": "杜甫",
                            "Title": "小寒食舟中作",
                            "Clause": "片片輕鷗下急湍",
                        }
                    ],
                }
            ]
        }

    monkeypatch.setattr(provider, "_request_json", fake_request_json)

    items = asyncio.run(
        provider.search(
            "片片轻鸥落晚沙",
            evidence_type="reference",
        )
    )

    assert len(items) == 1
    item = items[0]
    assert item.type == "reference"
    assert item.anchor == "片片轻鸥落晚沙"
    assert item.text == "片片輕鷗下急湍"
    assert item.source is not None
    assert item.source.title == "小寒食舟中作"
    assert item.source.author == "杜甫"
    assert item.metadata == {
        "dynasty": "唐",
        "writing_id": 30573,
    }
