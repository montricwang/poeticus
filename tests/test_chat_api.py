from fastapi.testclient import TestClient

import api


client = TestClient(api.app)


def test_chat_model_failure(monkeypatch):
    def fake_failure(*args, **kwargs):
        raise RuntimeError("DeepSeek API 调用失败")

    monkeypatch.setattr(api, "chat_about_poem", fake_failure)

    response = client.post(
        "/chat",
        json={
            "poem": "萧萧乱叶报新秋。",
            "question": "解释报字",
            "selection": None,
        },
    )

    assert response.status_code == 502
    assert response.json() == {"detail": "DeepSeek API 调用失败"}
