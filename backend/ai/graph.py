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
from openai.types.chat.completion_create_params import (
    CompletionCreateParamsNonStreaming,
    CompletionCreateParamsStreaming,
)

from backend.ai.model import client
from backend.config import AGENT_MAX_TOOL_CALLS, LLM_MAX_OUTPUT_TOKENS, LLM_MODEL
from backend.evidence.service import EvidenceService
from backend.evidence.providers.cnkgraph import CNKGraphProvider, CNKGraphError
from backend.ai.context import PoemContext, format_poem_context
from backend.ai.prompt_loader import compose_prompt
from backend.retrieval.client import (
    CurrentPoem,
    RetrievalClientError,
    text_retrieval_client,
)

logger = logging.getLogger(__name__)

_FINAL_AFTER_TOOL_BUDGET = (
    "工具调用预算已用完。现在必须直接回答用户，不要再尝试调用工具，"
    "也不要输出任何工具调用协议、标记或伪代码。"
    "只能基于已有对话、工具结果和自身知识作答；"
    "如果仍不能可靠确认，就明确说明不能确认。"
)
_TOOL_PROTOCOL_FALLBACK = (
    "这次检索流程没有形成可可靠展示的最终回答；"
    "我暂时不把未核实的内容当作结论。"
)


def _looks_like_tool_protocol(text: str) -> bool:
    """拦截模型把内部工具协议当普通正文吐出的情况。"""
    return "DSML" in text and ("invoke" in text or "calls" in text)


def _final_messages_without_tools(
    messages: list[ChatCompletionMessageParam],
) -> list[ChatCompletionMessageParam]:
    """工具预算耗尽后，明确切换到只能产出最终正文的模式。"""
    final_messages = [dict(message) for message in messages]

    if final_messages and final_messages[0].get("role") == "system":
        content = final_messages[0].get("content")
        if isinstance(content, str):
            final_messages[0]["content"] = (
                f"{content}\n\n{_FINAL_AFTER_TOOL_BUDGET}"
            )

    return cast(
        list[ChatCompletionMessageParam],
        final_messages,
    )


def _safe_final_answer(answer: str) -> str:
    if _looks_like_tool_protocol(answer):
        return _TOOL_PROTOCOL_FALLBACK
    return answer


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
                "查询中国古典诗词中的人物故事、掌故、神话传说和典故性短语的出处或含义。"
                "适合回答‘这个典故是什么故事/什么意思’；"
                "如果用户明确问‘借了谁哪一句诗、化用了哪段前代文本’，"
                "不要用本工具，应优先使用 search_predecessor_texts。"
                "不要用于整句诗文的全文相似检索、作品创作年代、作者生平、"
                "诗中人物身份或普通文学赏析。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "term": {
                        "type": "string",
                        "description": (
                            "真正需要查询的典故词语或短语。"
                            "优先使用最短且有辨识度的锚点；"
                            "不要机械地把整句诗、整段选区作为查询词。"
                        ),
                    }
                },
                "required": ["term"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_reference",
            "description": (
                "从外部诗词知识来源查询一句或短句可能对应的前代诗文、成句或化用候选。"
                "适合核对已有外部 reference evidence；"
                "返回结果只是候选，可能包含当前作品或后代作品，"
                "必须结合作者年代和文本关系判断。"
                "不适合解释人物故事型典故，也不能保证识别高度压缩或反用。"
                "若 search_predecessor_texts 可用，同一个文本来源问题不要先用本工具重复试探；"
                "只有本地 Corpus Tool 不可用，或已有明确理由需要外部 reference evidence 时再使用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": (
                            "真正要比较来源的诗句或短句。"
                            "优先只提交目标短句，不要机械地提交整首诗。"
                        ),
                    }
                },
                "required": ["text"],
                "additionalProperties": False,
            },
        },
    }
]

TEXT_RETRIEVAL_TOOL: ChatCompletionFunctionToolParam = {
    "type": "function",
    "function": {
        "name": "search_predecessor_texts",
        "description": (
            "在 Poeticus 自建古典诗词 Corpus 中检索可能对应当前文本的前代候选。"
            "用户问‘借了谁哪一句诗、化用了哪段前代文本、和哪一句前代文本有关’时，"
            "应优先使用本工具，即使目标短语同时带有典故色彩。"
            "适合寻找近似成句、改写、拆取重组和长尾互文；"
            "这是全文检索候选发现，不等于已经证明引用或化用。"
            "普通赏析、作者生平和人物故事型典故不要调用。"
            "如果第一轮结果不足，而问题仍然是文本来源，"
            "可以换一个更有辨识度的文本锚点再检索一次。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": (
                        "真正需要寻找前代文本的目标诗句或短片段。"
                        "优先保留有辨识度的原文；不要机械提交整首作品，"
                        "也不要把自己猜测的出处改写成 Query。"
                    ),
                }
            },
            "required": ["text"],
            "additionalProperties": False,
        },
    },
}


def _available_tools() -> list[ChatCompletionFunctionToolParam]:
    """Only expose the local-corpus tool when its service endpoint is configured."""
    if text_retrieval_client.enabled:
        return [*TOOLS, TEXT_RETRIEVAL_TOOL]
    return list(TOOLS)


class HistoryMessage(TypedDict):
    role: Literal["user", "assistant"]
    content: str


class ToolCall(TypedDict):
    id: str
    name: str
    arguments: str


class ToolResult(TypedDict):
    id: str
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
    evidences: NotRequired[list[dict[str, object]]]
    tool_calls: NotRequired[list[ToolCall]]
    tool_results: NotRequired[list[ToolResult]]
    stream_reply: NotRequired[bool]


class RouterUpdate(TypedDict, total=False):
    """LangGraph nodes return only the state fields they changed."""

    messages: list[ChatCompletionMessageParam]
    tool_count: int
    reply: str
    evidences: list[dict[str, object]]
    tool_calls: list[ToolCall]
    tool_results: list[ToolResult]


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
    tools_enabled: bool,
) -> tuple[str, list[ToolCall]]:
    writer = get_stream_writer()

    request_messages = (
        messages
        if tools_enabled
        else _final_messages_without_tools(messages)
    )

    request_kwargs: CompletionCreateParamsStreaming = {
        "model": LLM_MODEL,
        "max_tokens": LLM_MAX_OUTPUT_TOKENS,
        "messages": request_messages,
        "temperature": 0,
        "stream": True,
    }
    if tools_enabled:
        request_kwargs["tools"] = _available_tools()
        request_kwargs["tool_choice"] = "auto"

    parts: list[str] = []
    pending: dict[int, ToolCall] = {}
    finish_reason = None
    stream = None
    tool_calls_started = False

    try:
        stream = client.chat.completions.create(
            **request_kwargs,
            extra_body={"thinking": {"type": "disabled"}},
        )

        for chunk in stream:
            if not chunk.choices:
                continue

            choice = chunk.choices[0]
            delta = choice.delta

            # 工具调用可能分散在多个流式分片中。
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

            # 工具仍可用时保持正常流式输出；预算耗尽后的最后一轮
            # 先缓冲全文，避免内部协议片段直接泄漏到 SSE。
            if delta.content and not tool_calls_started:
                parts.append(delta.content)

                if tools_enabled:
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
        if not tools_enabled:
            answer = _TOOL_PROTOCOL_FALLBACK
            writer({"type": "token", "text": answer})
            return answer, []

        if finish_reason != "tool_calls":
            raise RuntimeError(f"工具调用未正常结束：{finish_reason}")

        calls = [pending[index] for index in sorted(pending)]

        for call in calls:
            if not call["id"] or not call["name"] or not call["arguments"]:
                raise RuntimeError("流式工具调用信息不完整")

        return "", calls

    if finish_reason != "stop":
        raise RuntimeError(f"模型未正常完成：{finish_reason}")

    answer = _safe_final_answer("".join(parts))

    if not answer.strip():
        raise RuntimeError("模型返回了空回答")

    if not tools_enabled:
        writer({"type": "token", "text": answer})

    return answer, []


def agent_decide(state: RouterState) -> RouterUpdate:
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

    tools_enabled = state.get("tool_count", 0) < AGENT_MAX_TOOL_CALLS

    stream_reply = state.get("stream_reply", False)
    tool_calls: list[ToolCall]

    if stream_reply:
        answer, tool_calls = _stream_agent_decision(messages, tools_enabled)
    else:
        request_messages = (
            messages
            if tools_enabled
            else _final_messages_without_tools(messages)
        )
        request_kwargs: CompletionCreateParamsNonStreaming = {
            "model": LLM_MODEL,
            "max_tokens": LLM_MAX_OUTPUT_TOKENS,
            "messages": request_messages,
            "temperature": 0,
        }
        if tools_enabled:
            request_kwargs["tools"] = _available_tools()
            request_kwargs["tool_choice"] = "auto"

        try:
            response = client.chat.completions.create(
                **request_kwargs,
                extra_body={"thinking": {"type": "disabled"}},
            )
        except APIError as exc:
            raise RuntimeError("Agent 决策 API 调用失败") from exc

        if not response.choices:
            raise RuntimeError("模型没有返回结果")

        message = response.choices[0].message

        if message.tool_calls and tools_enabled:
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
        elif message.tool_calls:
            tool_calls = []
            answer = _TOOL_PROTOCOL_FALLBACK
        else:
            tool_calls = []
            answer = _safe_final_answer(message.content or "")

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


def execute_tools(state: RouterState) -> RouterUpdate:
    calls = state.get("tool_calls") or []

    if not calls:
        raise RuntimeError("没有待执行的工具调用")

    messages = list(state.get("messages") or [])
    tool_count = state.get("tool_count", 0)

    # 防止重复 ID 使工具结果无法正确对应。
    ids = [call["id"] for call in calls]
    if len(ids) != len(set(ids)):
        raise RuntimeError("工具调用 ID 重复")

    async def run_tools() -> tuple[list[ToolResult], list[dict[str, object]], int]:
        results: list[ToolResult] = []
        all_evidences: list[dict[str, object]] = []
        count = tool_count

        for call in calls:
            if count >= AGENT_MAX_TOOL_CALLS:
                result = {
                    "status": "budget_exceeded",
                    "message": "本次请求的工具调用预算已用完",
                    "evidences": [],
                }
            else:
                count += 1

                try:
                    arguments = json.loads(call["arguments"])

                    if not isinstance(arguments, dict):
                        raise ValueError("工具参数必须是对象")

                    if call["name"] == "lookup_allusion":
                        query = arguments.get("term")
                        evidence_type = "allusion"
                        max_items = 3
                        invalid_message = "无效的典故查询词"
                    elif call["name"] == "lookup_reference":
                        query = arguments.get("text")
                        evidence_type = "reference"
                        max_items = 5
                        invalid_message = "无效的出处查询文本"
                    elif call["name"] == "search_predecessor_texts":
                        query = arguments.get("text")
                        evidence_type = "text_retrieval"
                        max_items = 8
                        invalid_message = "无效的 Text Retrieval 查询文本"
                    else:
                        raise ValueError(f"未知工具：{call['name']}")

                    if (
                        not isinstance(query, str)
                        or not query.strip()
                        or len(query) > 120
                    ):
                        raise ValueError(invalid_message)

                    query = query.strip()

                    if call["name"] == "search_predecessor_texts":
                        context = state.get("context")
                        retrieval = await text_retrieval_client.search(
                            text=query,
                            current_poem=CurrentPoem(
                                text=state["poem"],
                                title=(context.title if context else None),
                                author=(context.author if context else None),
                                dynasty=(context.dynasty if context else None),
                            ),
                            top_k=max_items,
                        )
                        items = []
                        for candidate in retrieval.candidates[:max_items]:
                            data = candidate.model_dump()
                            data["text"] = data["text"][:800]
                            if isinstance(data.get("title"), str):
                                data["title"] = data["title"][:200]
                            items.append(data)
                        result = {
                            "status": retrieval.status,
                            "query": query,
                            "evidence_type": evidence_type,
                            "candidates": items,
                            "note": (
                                "这些是 Corpus 文本候选，不自动证明引用、化用或影响关系；"
                                "请结合年代、全文上下文和文本对应关系判断。"
                            ),
                        }
                    else:
                        evidences = await evidence_service.search(
                            query=query,
                            provider_name="cnkgraph",
                            evidence_type=evidence_type,
                        )

                        # 限制回传给后续 LLM 轮次的工具材料长度，避免外部证据
                        # 带入过长文本。reference 多保留两条候选，便于跨年代比较。
                        items = []
                        for item in evidences[:max_items]:
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
                            "query": query,
                            "evidence_type": evidence_type,
                            "evidences": items,
                        }

                except (
                    ValueError,
                    KeyError,
                    TypeError,
                    CNKGraphError,
                    RetrievalClientError,
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

    # agent_decide 已经把 assistant 的工具调用加入 messages，
    # 这里仅追加对应的工具回复。
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
        "tool_results": [
            *(state.get("tool_results") or []),
            *results,
        ],
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

# 工具执行后不直接结束，把结果交还 Agent，由它决定下一步。
builder.add_edge("tools", "agent")

graph = builder.compile()
