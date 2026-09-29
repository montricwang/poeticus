"""测试 LangGraph 意图路由及各分支，不调用真实 API。"""

import json
from types import SimpleNamespace

import pytest

from backend.evidence.schema import EvidenceItem
from poem_context import PoemContext, format_poem_context

SAMPLE_CONTEXT = PoemContext(
    id="su-shi-huan-xi-sha-feng-juan-zhu-lian",
    title="浣溪沙·新秋",
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


@pytest.mark.parametrize(
    ("intent", "expected_step", "selection"),
    [
        ("text_reading", "direct_answer", "报"),
        ("source_lookup", "source_lookup", "三星当户"),
        ("needs_clarification", "needs_clarification", None),
    ],
)
def test_graph_routes_and_only_direct_branch_generates_answer(
    monkeypatch,
    router,
    intent,
    expected_step,
    selection,
):
    model_calls = []
    direct_calls = []
    search_calls = []
    evidence_answer_calls = []

    # 模拟意图分类模型
    def fake_create(**kwargs):
        model_calls.append(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    finish_reason="stop",
                    message=SimpleNamespace(
                        content=json.dumps(
                            {
                                "intent": intent,
                                "reason": "测试分类",
                            }
                        )
                    ),
                )
            ],
            usage=None,
        )

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))
    )

    # 模拟直接细读
    def fake_direct_answer(**kwargs):
        direct_calls.append(kwargs)
        return "模拟细读回答"

    # 模拟 EvidenceService
    async def fake_search(
        query,
        *,
        provider_name,
        evidence_type=None,
    ):
        search_calls.append(
            {
                "query": query,
                "provider_name": provider_name,
                "evidence_type": evidence_type,
            }
        )

        return [
            EvidenceItem(
                anchor=query,
                type="allusion",
                text="模拟文献引文",
                provider="cnkgraph",
                status="candidate",
            )
        ]

    # 模拟根据证据生成答案
    def fake_evidence_answer(**kwargs):
        evidence_answer_calls.append(kwargs)
        return "模拟证据回答"

    monkeypatch.setattr(router, "client", fake_client)
    monkeypatch.setattr(
        router,
        "chat_about_poem",
        fake_direct_answer,
    )
    monkeypatch.setattr(
        router.evidence_service,
        "search",
        fake_search,
    )
    monkeypatch.setattr(
        router,
        "answer_with_evidence",
        fake_evidence_answer,
    )

    # 真正运行 Graph，但所有外部调用都已被替换
    result = router.graph.invoke(
        {
            "poem": "萧萧乱叶报新秋。",
            "question": "测试问题",
            "selection": selection,
            "context": SAMPLE_CONTEXT,
        }
    )

    assert len(model_calls) == 1
    assert result["intent"] == intent
    assert result["next_step"] == expected_step
    assert isinstance(result["reply"], str)
    assert result["reply"]

    if intent == "text_reading":
        assert result["reply"] == "模拟细读回答"
        assert direct_calls == [
            {
                "poem": "萧萧乱叶报新秋。",
                "question": "测试问题",
                "selection": selection,
                "context": SAMPLE_CONTEXT,
            }
        ]
        assert search_calls == []
        assert evidence_answer_calls == []

    elif intent == "source_lookup":
        assert result["reply"] == "模拟证据回答"
        assert direct_calls == []

        assert search_calls == [
            {
                "query": "三星当户",
                "provider_name": "cnkgraph",
                "evidence_type": "allusion",
            }
        ]

        assert len(evidence_answer_calls) == 1
        assert evidence_answer_calls[0]["context"] == SAMPLE_CONTEXT
        assert len(result["evidences"]) == 1
        assert result["evidences"][0]["anchor"] == "三星当户"

    else:
        assert direct_calls == []
        assert search_calls == []
        assert evidence_answer_calls == []


def test_classifier_rejects_unknown_intent(monkeypatch, router):
    """模型返回不符合 Schema 的意图时，应当报错。"""

    def fake_create(**kwargs):
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    finish_reason="stop",
                    message=SimpleNamespace(
                        content=json.dumps(
                            {
                                "intent": "unknown",
                                "reason": "测试非法标签",
                            }
                        )
                    ),
                )
            ],
            usage=None,
        )

    monkeypatch.setattr(
        router,
        "client",
        SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))
        ),
    )

    with pytest.raises(RuntimeError, match="不符合 Schema"):
        router.classify_intent(
            {
                "poem": "萧萧乱叶报新秋。",
                "question": "解释报字",
                "context": SAMPLE_CONTEXT,
            }
        )


def test_classifier_receives_poem_context(monkeypatch, router):
    model_calls = []

    def fake_create(**kwargs):
        model_calls.append(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    finish_reason="stop",
                    message=SimpleNamespace(
                        content=json.dumps(
                            {
                                "intent": "text_reading",
                                "reason": "测试",
                            }
                        )
                    ),
                )
            ],
            usage=None,
        )

    monkeypatch.setattr(
        router,
        "client",
        SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))
        ),
    )

    result = router.classify_intent(
        {
            "poem": "萧萧乱叶报新秋。",
            "question": "解释报字",
            "selection": None,
            "context": SAMPLE_CONTEXT,
        }
    )

    assert result["intent"] == "text_reading"
    user_content = model_calls[0]["messages"][1]["content"]
    assert format_poem_context(SAMPLE_CONTEXT) in user_content
    assert "作者：苏轼" in user_content
    assert "imported_unreviewed" not in user_content


def test_classifier_and_graph_work_without_context(monkeypatch, router):
    """旧请求不带 context 时，分类与细读分支仍能正常工作。"""

    model_calls = []

    def fake_create(**kwargs):
        model_calls.append(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    finish_reason="stop",
                    message=SimpleNamespace(
                        content=json.dumps(
                            {
                                "intent": "text_reading",
                                "reason": "测试",
                            }
                        )
                    ),
                )
            ],
            usage=None,
        )

    monkeypatch.setattr(
        router,
        "client",
        SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))
        ),
    )
    monkeypatch.setattr(
        router,
        "chat_about_poem",
        lambda **kwargs: "模拟细读回答",
    )

    result = router.graph.invoke(
        {
            "poem": "萧萧乱叶报新秋。",
            "question": "解释报字",
            "selection": None,
        }
    )

    assert result["intent"] == "text_reading"
    assert result["next_step"] == "direct_answer"
    assert result["reply"] == "模拟细读回答"
    user_content = model_calls[0]["messages"][1]["content"]
    assert "作品上下文" not in user_content


def test_format_poem_context_notes_only_imported_unreviewed():
    assert format_poem_context(None) == ""

    unreviewed = format_poem_context(SAMPLE_CONTEXT)
    assert "题名：浣溪沙·新秋" in unreviewed
    assert "作者：苏轼" in unreviewed
    assert "时代：宋" in unreviewed
    assert "imported_unreviewed" not in unreviewed
    assert "尚未完成全面校勘" in unreviewed

    reviewed = format_poem_context(
        PoemContext(
            id="other-work",
            title="其他作品",
            author="某某",
            dynasty="唐",
            review_status="reviewed",
        )
    )
    assert "题名：其他作品" in reviewed
    assert "作者：某某" in reviewed
    assert "时代：唐" in reviewed
    assert "尚未完成全面校勘" not in reviewed
