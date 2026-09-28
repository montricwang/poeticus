"""评测脚本自身的离线测试，确保不会意外执行回答分支。"""


def test_evaluator_calls_only_classifier(monkeypatch, capsys):
    monkeypatch.setenv("LLM_API_KEY", "test-only-placeholder")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    from evals import evaluate_router

    calls = []

    def fake_classify(state):
        calls.append(state)
        return {"intent": "source_lookup", "reason": "测试分类"}

    monkeypatch.setattr(evaluate_router, "classify_intent", fake_classify)
    evaluate_router.main(["--case", "R011"])

    assert len(calls) == 1
    assert calls[0]["question"] == "这个字怎么读？"
    assert calls[0]["selection"] == "縠"
    assert "首选路径命中：1/1" in capsys.readouterr().out
