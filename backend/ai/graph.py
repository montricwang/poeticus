import asyncio
import logging
import json
from typing import Literal, NotRequired, TypedDict, cast
from langgraph.config import get_stream_writer
from langgraph.graph import StateGraph, START, END
from openai import APIError
from openai.types.chat import (
    ChatCompletionFunctionToolParam,
    ChatCompletionMessageParam,
)

from backend.ai.model import client, MAX_LLM_OUTPUT_TOKENS
from backend.evidence.service import EvidenceService
from backend.evidence.providers.cnkgraph import CNKGraphProvider, CNKGraphError
from backend.ai.context import PoemContext, format_poem_context
from backend.ai.prompt_loader import compose_prompt

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


class HistoryMessage(TypedDict):
    role: Literal["user", "assistant"]
    content: str


class RouterState(TypedDict):
    poem: str
    question: str
    context: NotRequired[PoemContext | None]
    selection: NotRequired[str | None]
    history: NotRequired[list[HistoryMessage]]
    messages: NotRequired[list[ChatCompletionMessageParam]]
    tool_count: NotRequired[int]
    reply: NotRequired[str]
    evidences: NotRequired[list[dict]]
    tool_calls: NotRequired[list[dict]]
    tool_results: NotRequired[list[dict]]
    stream_reply: NotRequired[bool]


def _agent_user_message(state: RouterState) -> str:
    return (
        f"{format_poem_context(state.get('context'))}"
        f"当前诗歌：\n{state['poem']}\n\n"
        f"当前选区：\n"
        f"{state.get('selection') or '（未选择任何原文）'}\n\n"
        f"用户问题：\n{state['question']}"
    )


def _stream_agent_decision(
    messages: list[ChatCompletionMessageParam],
    tool_choice: Literal["auto", "none"],
) -> tuple[str, list[dict]]:
    writer = get_stream_writer()

    parts: list[str] = []
    pending: dict[int, dict] = {}
    finish_reason = None
    stream = None
    tool_calls_started = False

    try:
        stream = client.chat.completions.create(
            model="deepseek-flash",
            max_tokens=MAX_LLM_OUTPUT_TOKENS,
            messages=messages,
            tools=TOOLS,
            tool_choice=tool_choice,
            temperature=0,
            stream=True,
            extra_body={"thinking": {"type": "disabled"}},
        )

        for chunk in stream:
            if not chunk.choices:
                continue

            choice = chunk.choices[0]
            delta = choice.delta

            # 工具调用可能分散在多个 chunk 中。
            for call in delta.tool_calls or []:
                if not tool_calls_started:
                    tool_calls_started = True

                item = pending.setdefault(
                    call.index,
                    {
                        "id": "",
                        "name": "",
                        "arguments": "",
                    },
                )

                if call.id:
                    item["id"] = call.id

                if call.function:
                    if call.function.name:
                        item["name"] += call.function.name

                    if call.function.arguments:
                        item["arguments"] += call.function.arguments

            # 只有纯文字回答才向前端发送 token。
            if delta.content:
                if not tool_calls_started:
                    parts.append(delta.content)

                    if delta.content:
                        writer(
                            {
                                "type": "token",
                                "text": delta.content,
                            }
                        )

            if choice.finish_reason is not None:
                finish_reason = choice.finish_reason

    except APIError as exc:
        raise RuntimeError("Agent 流式请求失败") from exc

    finally:
        if stream is not None:
            stream.close()

    if pending:
        if finish_reason != "tool_calls":
            raise RuntimeError(f"工具调用未正常结束：{finish_reason}")

        calls = [pending[index] for index in sorted(pending)]

        for call in calls:
            if not call["id"] or not call["name"] or not call["arguments"]:
                raise RuntimeError("流式工具调用信息不完整")

        return "", calls

    if finish_reason != "stop":
        raise RuntimeError(f"模型未正常完成：{finish_reason}")

    answer = "".join(parts)

    if not answer.strip():
        raise RuntimeError("模型返回了空回答")

    return answer, []


def agent_decide(state: RouterState) -> dict:
    # 第一次进入 Agent 时建立消息历史；
    # 再次进入时沿用已有记录。
    messages = list(state.get("messages") or [])

    if not messages:
        messages = [
            {
                "role": "system",
                "content": compose_prompt(
                    "agent_decide",
                    "output_style",
                ),
            },
        ]

        # 跨用户轮次的有效对话历史。
        # 这里只在 Agent 第一次启动时加入；
        # 工具执行后再次进入 Agent 时沿用 messages，
        # 避免重复插入历史。
        for message in state.get("history") or []:
            messages.append(
                {
                    "role": message["role"],
                    "content": message["content"],
                }
            )

        messages.append(
            {
                "role": "user",
                "content": _agent_user_message(state),
            }
        )

    messages = cast(
        list[ChatCompletionMessageParam],
        messages,
    )

    tool_choice: Literal["auto", "none"] = (
        "none" if state.get("tool_count", 0) >= 2 else "auto"
    )

    stream_reply = state.get("stream_reply", False)

    if stream_reply:
        answer, tool_calls = _stream_agent_decision(messages, tool_choice)
    else:
        try:
            response = client.chat.completions.create(
                model="deepseek-flash",
            max_tokens=MAX_LLM_OUTPUT_TOKENS,
                messages=messages,
                tools=TOOLS,
                tool_choice=tool_choice,
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
            answer = message.content or ""
        else:
            tool_calls = []
            answer = message.content or ""

    if tool_calls:
        messages.append(
            {
                "role": "assistant",
                "content": answer,
                "tool_calls": [
                    {
                        "id": call["id"],
                        "type": "function",
                        "function": {
                            "name": call["name"],
                            "arguments": call["arguments"],
                        },
                    }
                    for call in tool_calls
                ],
            }
        )
        return {
            "messages": messages,
            "tool_calls": tool_calls,
        }

    if not answer or not answer.strip():
        raise RuntimeError("模型既没有回答，也没有调用工具")

    messages.append(
        {
            "role": "assistant",
            "content": answer,
        }
    )
    return {
        "messages": messages,
        "reply": answer,
        "tool_calls": [],
    }


def route_agent(state: RouterState) -> Literal["tools", "done"]:
    if state.get("tool_calls"):
        return "tools"
    return "done"


def execute_tools(state: RouterState) -> dict:
    calls = state.get("tool_calls") or []

    if not calls:
        raise RuntimeError("没有待执行的工具调用")

    messages = list(state.get("messages") or [])
    tool_count = state.get("tool_count", 0)

    # 一次用户请求最多执行 8 次实际工具调用。
    max_tool_calls = 2

    # 防止重复 ID 使工具结果无法正确对应。
    ids = [call["id"] for call in calls]
    if len(ids) != len(set(ids)):
        raise RuntimeError("工具调用 ID 重复")

    async def run_tools():
        results = []
        all_evidences = []
        count = tool_count

        for call in calls:
            if count >= max_tool_calls:
                result = {
                    "status": "budget_exceeded",
                    "message": "本次请求的工具调用预算已用完",
                    "evidences": [],
                }
            else:
                count += 1

                try:
                    if call["name"] != "lookup_allusion":
                        raise ValueError(f"未知工具：{call['name']}")

                    arguments = json.loads(call["arguments"])

                    if not isinstance(arguments, dict):
                        raise ValueError("工具参数必须是对象")

                    term = arguments.get("term")

                    if not isinstance(term, str) or not term.strip() or len(term) > 64:
                        raise ValueError("无效的典故查询词")

                    term = term.strip()

                    evidences = await evidence_service.search(
                        query=term,
                        provider_name="cnkgraph",
                        evidence_type="allusion",
                    )

                    # Upper-bound tool material fed back into subsequent LLM
                    # turns; external evidence might contain huge passages.
                    items = []
                    for item in evidences[:3]:
                        data = item.model_dump()
                        data["text"] = data["text"][:1600]
                        if isinstance(data.get("source"), dict):
                            title = data["source"].get("title")
                            if isinstance(title, str):
                                data["source"]["title"] = title[:200]
                        items.append(data)

                    all_evidences.extend(items)

                    result = {
                        "status": ("ok" if items else "no_hit"),
                        "query": term,
                        "evidences": items,
                    }

                except (
                    ValueError,
                    KeyError,
                    TypeError,
                    CNKGraphError,
                ) as exc:
                    logger.warning(
                        "工具执行失败：%s",
                        exc,
                    )

                    result = {
                        "status": "error",
                        "message": str(exc),
                        "evidences": [],
                    }

            content = json.dumps(
                result,
                ensure_ascii=False,
            )

            results.append(
                {
                    "id": call["id"],
                    "content": content,
                }
            )

        return results, all_evidences, count

    results, evidences, new_count = asyncio.run(run_tools())

    # agent_decide 已经将 assistant 的工具调用
    # 加入 messages，这里只追加对应的工具回复。
    for result in results:
        messages.append(
            {
                "role": "tool",
                "tool_call_id": result["id"],
                "content": result["content"],
            }
        )

    return {
        "messages": messages,
        "tool_results": results,
        "tool_count": new_count,
        "evidences": [
            *(state.get("evidences") or []),
            *evidences,
        ],
    }


builder = StateGraph(RouterState)

builder.add_node("agent", agent_decide)
builder.add_node("tools", execute_tools)

builder.add_edge(START, "agent")

builder.add_conditional_edges(
    "agent",
    route_agent,
    {
        "tools": "tools",
        "done": END,
    },
)

# 工具执行后，不再直接进入最终回答节点。将工具结果交还给 Agent，由它重新决定下一步。
builder.add_edge("tools", "agent")

graph = builder.compile()
