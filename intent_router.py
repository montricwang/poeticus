from typing import Literal, NotRequired, TypedDict
from langgraph.config import get_stream_writer
from langgraph.graph import StateGraph, START, END
from openai import APIError
from pydantic import BaseModel, ValidationError

import asyncio
import re
import logging

from main import (
    client,
    chat_about_poem,
    stream_chat_about_poem,
    answer_with_evidence,
)
from backend.evidence.service import EvidenceService
from backend.evidence.providers.cnkgraph import (
    CNKGraphProvider,
    CNKGraphError,
)
from prompt_loader import load_prompt

logger = logging.getLogger(__name__)

evidence_service = EvidenceService(
    {
        "cnkgraph": CNKGraphProvider(),
    }
)


class IntentResult(BaseModel):
    intent: Literal[
        "text_reading",
        "source_lookup",
        "needs_clarification",
    ]
    reason: str


class RouterState(TypedDict):
    poem: str
    question: str
    selection: NotRequired[str | None]
    intent: NotRequired[str]
    reason: NotRequired[str]
    next_step: NotRequired[str]
    evidences: NotRequired[list[dict]]
    reply: NotRequired[str]
    # 仅 /chat/stream 传入；原有 /chat 不受影响。
    stream_reply: NotRequired[bool]


def classify_intent(state: RouterState) -> dict:
    system_prompt = load_prompt("classify_intent")

    try:
        response = client.chat.completions.create(
            model="deepseek-flash",
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": (
                        f"当前诗歌：\n{state['poem']}\n\n"
                        f"当前选区：\n"
                        f"{state.get('selection') or '（未选择任何原文）'}\n\n"
                        f"用户问题：\n{state['question']}"
                    ),
                },
            ],
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=512,
            extra_body={"thinking": {"type": "disabled"}},
        )
    except APIError as exc:
        raise RuntimeError("意图识别 API 调用失败") from exc

    if not response.choices:
        raise RuntimeError("模型没有返回分类结果")

    choice = response.choices[0]
    if choice.finish_reason != "stop":
        raise RuntimeError(
            f"模型提前停止：finish_reason={choice.finish_reason}，"
            f"content={choice.message.content!r}，"
            f"usage={response.usage}"
        )
    if not choice.message.content:
        raise RuntimeError(f"模型返回空内容：usage={response.usage}")
    try:
        decision = IntentResult.model_validate_json(choice.message.content)
    except ValidationError as exc:
        raise RuntimeError("意图分类结果不符合 Schema") from exc
    return {"intent": decision.intent, "reason": decision.reason}


def route_intent(
    state: RouterState,
) -> Literal["text_reading", "source_lookup", "needs_clarification"]:
    intent = state.get("intent")
    if intent in ("text_reading", "source_lookup", "needs_clarification"):
        return intent
    raise ValueError(f"缺少有效的意图分类结果：{intent!r}")


def direct_answer(state: RouterState) -> dict:
    if state.get("stream_reply"):
        # 只有流式端点走此分支；Graph 自定义事件直接转发 SDK 增量。
        writer = get_stream_writer()
        parts: list[str] = []
        for token in stream_chat_about_poem(
            poem=state["poem"],
            question=state["question"],
            selection=state.get("selection"),
        ):
            parts.append(token)
            writer({"type": "token", "text": token})
        answer = "".join(parts)
    else:
        answer = chat_about_poem(
            poem=state["poem"],
            question=state["question"],
            selection=state.get("selection"),
        )
    return {"next_step": "direct_answer", "reply": answer}


def source_lookup(state: RouterState) -> dict:
    question = state["question"].strip()
    selection = (state.get("selection") or "").strip()

    # 1. 确定查询对象：优先使用选区
    term = selection

    # 没有选区时，提取问题中带引号的词句
    if not term:
        quoted = re.search(
            r"[「“『]([^」”』]{1,30})[」”』]",
            question,
        )
        if quoted:
            term = quoted.group(1).strip()

    # 仍未找到时，识别几种明确的提问方式
    if not term:
        plain = re.match(
            r"^([\u3400-\u9fff]{1,12}?)"
            r"(?:"
            r"有哪些[^？?。]*典故"
            r"|的典故"
            r"|(?:这个词)?出自哪里"
            r"|有什么(?:文献)?出处"
            r")",
            question,
        )
        if plain:
            term = plain.group(1).strip()

    # 不允许把空字符串或模糊指代发送给 Provider
    if not term or term in {"这个", "这个词", "这句话", "这里"}:
        return {
            "next_step": "needs_clarification",
            "reply": ("请选中需要查证的词句，或在问题中明确指出查询对象。"),
        }

    # 2. 查询 EvidenceService
    try:
        evidences = asyncio.run(
            evidence_service.search(
                query=term,
                provider_name="cnkgraph",
                evidence_type="allusion",
            )
        )
    except CNKGraphError:
        logger.exception(
            "CNKGraph 查询失败，查询对象：%s",
            term,
        )
        return {
            "next_step": "source_lookup",
            "reply": "CNKGraph 查询失败，本次未能取得证据。",
        }

    # 3. 处理空结果
    if not evidences:
        return {
            "next_step": "source_lookup",
            "evidences": [],
            "reply": (f"没有检索到「{term}」的典故资料。这不代表它没有其他文献出处。"),
        }

    # 4. 让 LLM 结合原诗和候选证据生成回答
    try:
        answer = answer_with_evidence(
            poem=state["poem"],
            question=question,
            selection=selection or None,
            evidences=evidences,
        )
    except APIError as exc:
        raise RuntimeError("证据分析 API 调用失败") from exc

    # 5. 将回答和结构化证据写回 Graph State
    return {
        "next_step": "source_lookup",
        "evidences": [item.model_dump() for item in evidences],
        "reply": answer,
    }


def clarify_user(state: RouterState) -> dict:
    """向用户请求完成当前问题所必需的信息。"""
    return {
        "next_step": "needs_clarification",
        "reply": "你具体指诗中的哪个词或哪句话？可以选中原文，或者直接告诉我。",
    }


builder = StateGraph(RouterState)
builder.add_node("classify_intent", classify_intent)
builder.add_node("direct_answer", direct_answer)
builder.add_node("source_lookup", source_lookup)
builder.add_node("clarify_user", clarify_user)
builder.add_edge(START, "classify_intent")
builder.add_conditional_edges(
    "classify_intent",
    route_intent,
    {
        "text_reading": "direct_answer",
        "source_lookup": "source_lookup",
        "needs_clarification": "clarify_user",
    },
)
builder.add_edge("direct_answer", END)
builder.add_edge("source_lookup", END)
builder.add_edge("clarify_user", END)
graph = builder.compile()


if __name__ == "__main__":
    poem = (
        "风卷珠帘自上钩，萧萧乱叶报新秋。"
        "独携纤手上高楼。"
        "缺月向人舒窈窕，三星当户照绸缪。"
        "香生雾縠见纤柔。"
    )
    cases = [
        {
            "question": "这个词从哪来的？",
            "selection": "三星当户",
            "expected": "source_lookup",
        },
        {
            "question": "这个词从哪来的？",
            "selection": None,
            "expected": "needs_clarification",
        },
        {
            "question": "这个词我没听说过。",
            "selection": "绸缪",
            "expected": "text_reading",
        },
        {
            "question": "这是什么意思？",
            "selection": None,
            "expected": "needs_clarification",
        },
    ]
    for case in cases:
        result = graph.invoke(
            {"poem": poem, "question": case["question"], "selection": case["selection"]}
        )
        actual = result["intent"]
        expected = case["expected"]
        print(f"\n问题：{case['question']}")
        print(f"选区：{case['selection']}")
        print(f"预期：{expected}")
        print(f"实际：{actual}")
        print(f"结果：{'PASS' if actual == expected else 'FAIL'}")
        print(f"理由：{result['reason']}")
        if result.get("reply"):
            print(f"澄清：{result['reply']}")
