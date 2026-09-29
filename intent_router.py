import asyncio
import logging
import json
from typing import Literal, NotRequired, TypedDict
from langgraph.graph import StateGraph, START, END
from openai import APIError
from pydantic import BaseModel
from openai.types.chat import ChatCompletionFunctionToolParam

from main import client
from backend.evidence.service import EvidenceService
from backend.evidence.providers.cnkgraph import CNKGraphProvider, CNKGraphError
from poem_context import PoemContext, format_poem_context
from prompt_loader import compose_prompt

logger = logging.getLogger(__name__)

evidence_service = EvidenceService(
    {
        "cnkgraph": CNKGraphProvider(),
    }
)

TOOLS: list[ChatCompletionFunctionToolParam] = [
    {
        "type": "function",
        "function": {
            "name": "lookup_allusion",
            "description": (
                "查询中国古典诗词中的典故及其含义。"
                "仅在用户确实询问典故时使用。"
                "不要用于作品创作年代、作者生平、"
                "诗中人物身份或普通文学赏析。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "term": {
                        "type": "string",
                        "description": (
                            "真正需要查询的典故词语或短语。"
                            "不要机械地把整段选区作为查询词。"
                        ),
                    }
                },
                "required": ["term"],
                "additionalProperties": False,
            },
        },
    }
]


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
    context: NotRequired[PoemContext | None]
    selection: NotRequired[str | None]
    reply: NotRequired[str]
    evidences: NotRequired[list[dict]]
    tool_calls: NotRequired[list[dict]]
    stream_reply: NotRequired[bool]


def _agent_user_message(state: RouterState) -> str:
    return (
        f"{format_poem_context(state.get('context'))}"
        f"当前诗歌：\n{state['poem']}\n\n"
        f"当前选区：\n"
        f"{state.get('selection') or '（未选择任何原文）'}\n\n"
        f"用户问题：\n{state['question']}"
    )


def agent_decide(state: RouterState) -> dict:
    try:
        response = client.chat.completions.create(
            model="deepseek-flash",
            messages=[
                {
                    "role": "system",
                    "content": compose_prompt("agent_decide", "output_style"),
                },
                {
                    "role": "user",
                    "content": _agent_user_message(state),
                },
            ],
            tools=TOOLS,
            tool_choice="auto",
            temperature=0,
            extra_body={"thinking": {"type": "disabled"}},
        )
    except APIError as exc:
        raise RuntimeError("Agent 决策 API 调用失败") from exc

    if not response.choices:
        raise RuntimeError("模型没有返回结果")

    message = response.choices[0].message

    if message.tool_calls:
        tool_calls = []

        for call in message.tool_calls:
            if call.type != "function":
                raise RuntimeError(f"暂不支持的工具类型：{call.type}")

            tool_calls.append(
                {
                    "id": call.id,
                    "name": call.function.name,
                    "arguments": call.function.arguments,
                }
            )

        return {"tool_calls": tool_calls}

    if not message.content:
        raise RuntimeError("模型既没有回答，也没有调用工具")

    return {
        "reply": message.content,
        "tool_calls": [],
    }


def route_agent(state: RouterState) -> Literal["tools", "done"]:
    if state.get("tool_calls"):
        return "tools"
    return "done"


def execute_tools(state: RouterState) -> dict:
    calls = state.get("tool_calls") or []

    if len(calls) != 1:
        raise RuntimeError("当前版本每轮只允许一次工具调用")

    call = calls[0]

    if call["name"] != "lookup_allusion":
        raise RuntimeError(f"未知工具：{call['name']}")

    try:
        arguments = json.loads(call["arguments"])
    except json.JSONDecodeError as exc:
        raise RuntimeError("工具参数不是有效 JSON") from exc

    term = arguments.get("term")

    if not isinstance(term, str) or not term.strip():
        raise RuntimeError("lookup_allusion 缺少有效 term")

    term = term.strip()

    try:
        evidences = asyncio.run(
            evidence_service.search(
                query=term,
                provider_name="cnkgraph",
                evidence_type="allusion",
            )
        )
    except CNKGraphError:
        logger.exception("CNKGraph 查询失败")
        return {
            "evidences": [],
        }

    return {"evidences": [item.model_dump() for item in evidences]}


def answer_after_tool(state: RouterState) -> dict:
    calls = state.get("tool_calls") or []

    if not calls:
        raise RuntimeError("缺少工具调用信息")

    call = calls[0]
    evidences = state.get("evidences") or []

    tool_result = json.dumps(
        evidences,
        ensure_ascii=False,
    )

    try:
        response = client.chat.completions.create(
            model="deepseek-flash",
            messages=[
                {
                    "role": "system",
                    "content": compose_prompt("agent_after_tool", "output_style"),
                },
                {
                    "role": "user",
                    "content": _agent_user_message(state),
                },
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": call["id"],
                            "type": "function",
                            "function": {
                                "name": call["name"],
                                "arguments": call["arguments"],
                            },
                        }
                    ],
                },
                {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": tool_result,
                },
            ],
            temperature=0,
            extra_body={"thinking": {"type": "disabled"}},
        )
    except APIError as exc:
        raise RuntimeError("工具结果回答 API 调用失败") from exc

    if not response.choices:
        raise RuntimeError("模型没有返回最终回答")

    message = response.choices[0].message

    if not message.content:
        raise RuntimeError("模型返回了空回答")

    return {"reply": message.content}


builder = StateGraph(RouterState)

builder.add_node("agent", agent_decide)
builder.add_node("tools", execute_tools)
builder.add_node("answer_after_tool", answer_after_tool)

builder.add_edge(START, "agent")
builder.add_conditional_edges(
    "agent",
    route_agent,
    {"tools": "tools", "done": END},
)
builder.add_edge("tools", "answer_after_tool")
builder.add_edge("answer_after_tool", END)

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
