"""Poeticus 的 LangGraph 对话循环与工具执行入口。

Agent 基于当前作品、用户选区、对话历史作答，必要时调用证据或检索工具；
工具执行后将结果追加到本次消息，再交还 Agent 决定下一步。
普通回答和 SSE 流式回答共用这套图，不在这里处理 HTTP 请求校验。
"""

import asyncio
import logging
import json
from dataclasses import dataclass
from inspect import signature
from typing import Literal, NotRequired, TypedDict, cast
from langgraph.config import get_stream_writer
from langgraph.graph import StateGraph, START, END
from openai import APIError
from openai.types.chat import ChatCompletionMessageParam
from openai.types.chat.completion_create_params import (
    CompletionCreateParamsNonStreaming,
    CompletionCreateParamsStreaming,
)

from backend.ai.model import client
from backend.ai.tools import available_tools
from backend.ai.critic_skills import load_critic_skills, validate_skill_names
from backend.config import (
    AGENT_MAX_TOOL_CALLS,
    CNKGRAPH_RESEARCH_TOOLS_ENABLED,
    DEEPSEEK_WEB_TOOLS_ENABLED,
    CLASSIC_REFERENCE_TOOLS_ENABLED,
    LLM_MAX_OUTPUT_TOKENS,
    LLM_MODEL,
)
from backend.research.deepseek_web import DeepSeekWebClient, DeepSeekWebError
from backend.research.classic_references import ClassicReferencesClient, ReferenceSourceError
from backend.evidence.service import EvidenceService
from backend.evidence.providers.cnkgraph import CNKGraphProvider, CNKGraphError
from backend.evidence.providers.cnkgraph_research import (
    CNKGraphResearchClient,
    CNKGraphResearchError,
)
from backend.ai.context import PoemContext, format_poem_context
from backend.ai.prompt_loader import compose_prompt
from backend.retrieval.document.service import document_retrieval, DocumentRetrievalError
from backend.retrieval.poem.client import (
    CurrentPoem,
    RetrievalClientError,
    text_retrieval_client,
)

# ===== 1. 模型输出保护与工具配置 =====

logger = logging.getLogger(__name__)

_FINAL_AFTER_TOOL_BUDGET = (
    "工具调用预算已用完。现在必须直接回答用户，不要再尝试调用工具，"
    "也不要输出任何工具调用协议、标记或伪代码。"
    "只能基于已有对话、工具结果和自身知识作答；"
    "如果仍不能可靠确认，就明确说明不能确认。"
)
_TOOL_PROTOCOL_FALLBACK = (
    "这次检索流程没有形成可可靠展示的最终回答；我暂时不把未核实的内容当作结论。"
)


def _max_tool_calls_for_state(state: "AgentState") -> int:
    """Return the validated per-request budget, defaulting to deployment config."""
    value = state.get("max_tool_calls", AGENT_MAX_TOOL_CALLS)
    if type(value) is not int or not 1 <= value <= 10:
        raise ValueError("max_tool_calls must be an integer from 1 to 10")
    return value


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
            final_messages[0]["content"] = f"{content}\n\n{_FINAL_AFTER_TOOL_BUDGET}"

    return cast(
        list[ChatCompletionMessageParam],
        final_messages,
    )


def _safe_final_answer(answer: str) -> str:
    """检查最终回答中的工具协议残留，返回可以展示的正文。"""

    if _looks_like_tool_protocol(answer):
        return _TOOL_PROTOCOL_FALLBACK

    return answer


# 创建典故与出处查询服务，供工具执行节点使用。
evidence_service = EvidenceService(
    {
        "cnkgraph": CNKGraphProvider(),
    }
)
cnkgraph_research_client = CNKGraphResearchClient()
deepseek_web_client = DeepSeekWebClient()
classic_references_client = ClassicReferencesClient()


# ===== 2. 消息、工具调用与工作流状态 =====


class HistoryMessage(TypedDict):
    """一次历史对话中的用户或助手消息。"""

    role: Literal["user", "assistant"]
    content: str


class ToolCall(TypedDict):
    """模型提出的工具调用，包括调用 ID、工具名和 JSON 参数。"""

    id: str
    name: str
    arguments: str


class ToolResult(TypedDict):
    """一次工具调用的结果，以调用 ID 对应原始请求。"""

    id: str
    content: str


@dataclass(frozen=True)
class _ToolQuery:
    """已经通过边界校验的工具查询；执行阶段不再解析模型原始参数。"""

    text: str
    evidence_type: Literal[
        "allusion", "reference", "text_retrieval", "commentary",
        "ci_meter", "classical_books", "ci_tune", "rhyme", "entities",
        "web_search", "web_fetch",
        "moedict", "wikisource_search", "wikisource_page", "critic_skill",
    ]
    max_items: int
    tune_name: str | None = None
    book: str | None = None
    category_id: str = ""
    character: str = ""
    epoch: str = ""
    url: str = ""
    source: str = "all"
    pageid: int = 0
    extra_queries: tuple[str, ...] = ()
    skill_names: tuple[str, ...] = ()


def _validate_registered_tool(call: ToolCall) -> None:
    """Only tools advertised to the model can be executed."""
    registered = {
        tool["function"]["name"]
        for tool in available_tools(
            text_retrieval_client.enabled,
            document_retrieval.enabled,
            CNKGRAPH_RESEARCH_TOOLS_ENABLED,
            DEEPSEEK_WEB_TOOLS_ENABLED,
            CLASSIC_REFERENCE_TOOLS_ENABLED,
        )
    }
    if call["name"] not in registered:
        # Disambiguate a model-invented function from a real but disabled one.
        # The registry grows with optional providers, so derive known names
        # from its actual signature instead of hardcoding old tool families.
        all_known = {
            tool["function"]["name"]
            for tool in available_tools(
                *(True for _ in signature(available_tools).parameters)
            )
        }
        if call["name"] not in all_known:
            raise ValueError(f"未知工具：{call['name']}")
        raise ValueError(f"本轮未开放工具：{call['name']}")


def _parse_tool_query(call: ToolCall) -> _ToolQuery:
    """解析工具名称和 JSON 参数，生成已校验的查询及结果数量上限。"""

    raw: object = json.loads(call["arguments"])
    if not isinstance(raw, dict):
        raise ValueError("工具参数必须是对象")
    # JSON 对象的 key 均为字符串，字段值仍在下方按工具契约校验。
    arguments = cast(dict[str, object], raw)

    if (
        call["name"] in (
            "analyze_ci_meter", "search_classical_books",
            "lookup_ci_tune", "lookup_rhyme", "resolve_entities",
        )
        and not CNKGRAPH_RESEARCH_TOOLS_ENABLED
    ):
        raise ValueError("CNKGraph 研究工具未启用")

    if call["name"] == "load_critic_skills":
        return _ToolQuery(
            text="", evidence_type="critic_skill", max_items=0,
            skill_names=validate_skill_names(arguments.get("skills")),
        )

    if call["name"] == "analyze_ci_meter":
        tune_name = arguments.get("tune_name")
        content = arguments.get("content", "")
        if not isinstance(tune_name, str) or not 1 <= len(tune_name.strip()) <= 40:
            raise ValueError("无效的词牌名")
        if not isinstance(content, str) or len(content) > 1200:
            raise ValueError("词律分析正文必须是至多 1200 字的文本")
        return _ToolQuery(
            text=content.strip(), evidence_type="ci_meter", max_items=0,
            tune_name=tune_name.strip(),
        )

    if call["name"] == "search_classical_books":
        query = arguments.get("query")
        if not isinstance(query, str) or not 1 <= len(query.strip()) <= 70:
            raise ValueError("古籍检索关键词必须为 1–70 字")
        return _ToolQuery(
            text=query.strip(), evidence_type="classical_books", max_items=5,
        )

    if call["name"] == "lookup_ci_tune":
        tune_name = arguments.get("tune_name")
        if not isinstance(tune_name, str) or not 1 <= len(tune_name.strip()) <= 40:
            raise ValueError("无效的词牌名")
        return _ToolQuery(
            text=tune_name.strip(), evidence_type="ci_tune", max_items=0,
        )

    if call["name"] == "lookup_rhyme":
        book = arguments.get("book")
        category_id = arguments.get("category_id", "")
        character = arguments.get("character", "")
        if book not in ("平水韵", "词林正韵", "中原音韵", "中华通韵"):
            raise ValueError("无效的韵书名")
        if not isinstance(category_id, str) or len(category_id) > 40:
            raise ValueError("无效的韵部 ID")
        if not isinstance(character, str) or len(character) > 1:
            raise ValueError("韵部字表一次只验证一个字")
        return _ToolQuery(
            text="", evidence_type="rhyme", max_items=0,
            book=book, category_id=category_id.strip(),
            character=character.strip(),
        )

    if call["name"] == "resolve_entities":
        content = arguments.get("text", "")
        epoch = arguments.get("epoch", "")
        if not isinstance(content, str) or len(content) > 450:
            raise ValueError("实体标注正文最多 450 字")
        if not isinstance(epoch, str) or len(epoch) > 24:
            raise ValueError("无效的历史时代")
        return _ToolQuery(
            text=content.strip(), evidence_type="entities", max_items=0,
            epoch=epoch.strip(),
        )

    if call["name"] in ("web_search", "web_fetch"):
        if not DEEPSEEK_WEB_TOOLS_ENABLED:
            raise ValueError("联网搜索工具未启用")
        if call["name"] == "web_search":
            query = arguments.get("query")
            source = arguments.get("source", "all")
            if not isinstance(query, str) or not 1 <= len(query.strip()) <= 100:
                raise ValueError("联网搜索关键词必须为 1–100 字")
            if source not in ("all", "zdic", "shidian", "ctext", "souyun", "wikimedia"):
                raise ValueError("不支持的联网来源")
            return _ToolQuery(
                text=query.strip(), evidence_type="web_search", max_items=5,
                source=source,
            )
        url = arguments.get("url")
        if not isinstance(url, str) or not 1 <= len(url) <= 2048:
            raise ValueError("无效的网页地址")
        return _ToolQuery(text="", evidence_type="web_fetch", max_items=0, url=url)

    if call["name"] in ("lookup_moedict", "search_wikisource", "read_wikisource_page"):
        if not CLASSIC_REFERENCE_TOOLS_ENABLED:
            raise ValueError("文献与词典工具未启用")
        if call["name"] == "read_wikisource_page":
            pageid = arguments.get("pageid")
            if type(pageid) is not int or pageid <= 0:
                raise ValueError("无效的维基文库 pageid")
            return _ToolQuery(
                text="", evidence_type="wikisource_page", max_items=0, pageid=pageid,
            )
        field = "term" if call["name"] == "lookup_moedict" else "query"
        text = arguments.get(field)
        upper = 16 if field == "term" else 100
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= upper:
            raise ValueError("无效的字词或文库查询文本")
        return _ToolQuery(
            text=text.strip(),
            evidence_type="moedict" if field == "term" else "wikisource_search",
            max_items=0 if field == "term" else 5,
        )

    # Document Query Expansion 是同一次工具调用的一部分；永远额外保留用户原始问题。
    if call["name"] == "search_documents":
        queries = arguments.get("queries")
        if (
            not isinstance(queries, list)
            or not 1 <= len(queries) <= 2
            or any(not isinstance(q, str) or not q.strip() or len(q) > 180 for q in queries)
        ):
            raise ValueError("无效的文献检索查询数组")
        return _ToolQuery(
            text=queries[0].strip(),
            evidence_type="commentary",
            max_items=5,
            extra_queries=tuple(q.strip() for q in queries[1:]),
        )

    # 根据工具名称选取查询字段、证据类型和返回条数。
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

    # 每次工具查询都需要有效且长度受限的文本。
    if not isinstance(query, str) or not query.strip() or len(query) > 120:
        raise ValueError(invalid_message)

    return _ToolQuery(
        text=query.strip(),
        evidence_type=evidence_type,
        max_items=max_items,
    )


class AgentState(TypedDict):
    """LangGraph 运行时的共享状态，保存问题、消息、工具结果和回答。"""

    poem: str
    question: str
    context: NotRequired[PoemContext | None]
    selection: NotRequired[str | None]
    history: NotRequired[list[HistoryMessage]]
    user_memory: NotRequired[list[str]]
    messages: NotRequired[list[ChatCompletionMessageParam]]
    tool_count: NotRequired[int]
    loaded_skills: NotRequired[list[str]]
    max_tool_calls: NotRequired[int]
    reply: NotRequired[str]
    evidences: NotRequired[list[dict[str, object]]]
    tool_calls: NotRequired[list[ToolCall]]
    tool_results: NotRequired[list[ToolResult]]
    stream_reply: NotRequired[bool]


class AgentStateUpdate(TypedDict, total=False):
    """LangGraph 节点只返回本轮更新过的状态字段。"""

    messages: list[ChatCompletionMessageParam]
    tool_count: int
    loaded_skills: list[str]
    reply: str
    evidences: list[dict[str, object]]
    tool_calls: list[ToolCall]
    tool_results: list[ToolResult]


# ===== 3. Agent 输入与模型请求 =====


def _agent_user_message(state: AgentState) -> str:
    """将当前作品、选区、阅读上下文和问题拼成用户消息。"""

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
    """流式请求模型，收集正文和工具调用，并通过 Graph 发送正文 token。"""

    # --- 3.1 准备请求消息与工具选项 ---

    writer = get_stream_writer()

    request_messages = (
        messages if tools_enabled else _final_messages_without_tools(messages)
    )

    request_kwargs: CompletionCreateParamsStreaming = {
        "model": LLM_MODEL,
        "max_tokens": LLM_MAX_OUTPUT_TOKENS,
        "messages": request_messages,
        "temperature": 0,
        "stream": True,
    }
    if tools_enabled:
        request_kwargs["tools"] = available_tools(
            text_retrieval_client.enabled,
            document_retrieval.enabled,
            CNKGRAPH_RESEARCH_TOOLS_ENABLED,
            DEEPSEEK_WEB_TOOLS_ENABLED,
            CLASSIC_REFERENCE_TOOLS_ENABLED,
        )
        request_kwargs["tool_choice"] = "auto"

    # --- 3.2 初始化正文与工具调用分片缓存 ---

    parts: list[str] = []
    pending: dict[int, ToolCall] = {}
    finish_reason = None
    stream = None
    tool_calls_started = False

    # --- 3.3 读取模型流式响应并拼接分片 ---

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
            # 普通正文按需即时发出；工具调用开始后继续收集工具参数。
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

    # --- 3.4 验证并返回工具调用或最终回答 ---

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


# ===== 4. Agent 决策与工作流路由 =====


def agent_decide(state: AgentState) -> AgentStateUpdate:
    """准备本轮对话，调用模型，并返回最终回答或工具调用请求。"""

    # --- 4.1 首次进入时建立模型消息历史 ---

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

        # Only a trusted server-side memory lookup may populate this field.
        # Treat extracted memories as fallible context, never as instructions
        # to override system policy or as independently verified poem facts.
        memory_notes = state.get("user_memory") or []
        if memory_notes:
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "以下为该读者以前明确表达的偏好或兴趣摘要。"
                        "仅在与本题相关时参考；它们可能过时，"
                        "不能用作诗歌史实证据或覆盖本轮用户要求。\n"
                        + json.dumps(memory_notes[:4], ensure_ascii=False)
                    ),
                }
            )

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

    # --- 4.2 根据工具预算及响应模式选择模型调用方式 ---

    tools_enabled = state.get("tool_count", 0) < _max_tool_calls_for_state(state)

    stream_reply = state.get("stream_reply", False)
    tool_calls: list[ToolCall]

    # 流式请求逐步接收事件，普通请求一次获取完整模型响应。
    if stream_reply:
        answer, tool_calls = _stream_agent_decision(messages, tools_enabled)
    else:
        request_messages = (
            messages if tools_enabled else _final_messages_without_tools(messages)
        )
        request_kwargs: CompletionCreateParamsNonStreaming = {
            "model": LLM_MODEL,
            "max_tokens": LLM_MAX_OUTPUT_TOKENS,
            "messages": request_messages,
            "temperature": 0,
        }
        if tools_enabled:
            request_kwargs["tools"] = available_tools(
                text_retrieval_client.enabled,
                document_retrieval.enabled,
                CNKGRAPH_RESEARCH_TOOLS_ENABLED,
                DEEPSEEK_WEB_TOOLS_ENABLED,
                CLASSIC_REFERENCE_TOOLS_ENABLED,
            )
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

        # 将模型提出的工具调用整理成内部 ToolCall 数据。
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

    # --- 4.3 将决策结果写回工作流状态 ---

    # 模型选择工具时保存调用信息，交给工具节点执行。
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

    # 模型直接回答时保存正文，供工作流结束后返回给 API。
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


def route_agent(state: AgentState) -> Literal["tools", "done"]:
    """根据模型是否提出工具调用，选择工具节点或结束本轮。"""

    if state.get("tool_calls"):
        return "tools"

    return "done"


# ===== 5. 工具执行与结果回传 =====


async def _execute_evidence_query(
    *,
    query: str,
    evidence_type: Literal["allusion", "reference"],
    max_items: int,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    """调用证据服务，整理 Agent 工具回复及写入 State 的证据。"""

    evidences = await evidence_service.search(
        query=query,
        provider_name="cnkgraph",
        evidence_type=evidence_type,
    )

    # 限制回传给模型的文本与来源标题长度，避免证据材料过长。

    evidence_items: list[dict[str, object]] = []
    for item in evidences[:max_items]:
        evidence_data: dict[str, object] = item.model_dump()
        evidence_data["text"] = item.text[:1600]
        source = evidence_data.get("source")
        if isinstance(source, dict):
            title = source.get("title")
            if isinstance(title, str):
                source["title"] = title[:200]
        evidence_items.append(evidence_data)

    result: dict[str, object] = {
        "status": "ok" if evidence_items else "no_hit",
        "query": query,
        "evidence_type": evidence_type,
        "evidences": evidence_items,
    }

    return result, evidence_items


def execute_tools(state: AgentState) -> AgentStateUpdate:
    """执行模型请求的工具，将查询结果和工具消息写回工作流状态。"""

    # --- 5.1 获取工具调用并检查调用 ID ---

    calls = state.get("tool_calls") or []

    if not calls:
        raise RuntimeError("没有待执行的工具调用")

    messages = list(state.get("messages") or [])
    tool_count = state.get("tool_count", 0)
    max_tool_calls = _max_tool_calls_for_state(state)
    loaded_skills = set(state.get("loaded_skills") or [])

    # 防止重复 ID 使工具结果无法正确对应。
    ids = [call["id"] for call in calls]
    if len(ids) != len(set(ids)):
        raise RuntimeError("工具调用 ID 重复")

    async def run_tools() -> tuple[list[ToolResult], list[dict[str, object]], int]:
        """依次执行查询，汇总工具响应、证据及调用次数。"""

        results: list[ToolResult] = []
        all_evidences: list[dict[str, object]] = []
        count = tool_count

        # Only URLs from actual successful web_search tool responses in THIS
        # Agent request may be fetched. No cross-user global cache.
        permitted_urls: set[str] = set()
        for prior in state.get("tool_results") or []:
            try:
                payload = json.loads(prior["content"])
            except (ValueError, KeyError, TypeError):
                continue
            if (
                isinstance(payload, dict)
                and payload.get("provider") == "deepseek_web"
                and payload.get("status") == "ok"
                and isinstance(payload.get("results"), list)
            ):
                permitted_urls.update(
                    item["url"]
                    for item in payload["results"]
                    if isinstance(item, dict) and isinstance(item.get("url"), str)
                )

        permitted_pageids: set[int] = set()
        for prior in state.get("tool_results") or []:
            try:
                payload = json.loads(prior["content"])
            except (ValueError, KeyError, TypeError):
                continue
            if (
                isinstance(payload, dict)
                and payload.get("provider") == "wikisource"
                and payload.get("status") == "ok"
                and isinstance(payload.get("results"), list)
            ):
                permitted_pageids.update(
                    item["pageid"] for item in payload["results"]
                    if isinstance(item, dict) and type(item.get("pageid")) is int
                )

        # --- 5.2 检查预算、解析参数并执行各项工具调用 ---

        for call in calls:
            result: dict[str, object]
            if count >= max_tool_calls and call["name"] != "load_critic_skills":
                result = {
                    "status": "budget_exceeded",
                    "message": "本次请求的工具调用预算已用完",
                    "evidences": [],
                }
            else:
                # Valid first-time local Skill loads do not consume the evidence-tool budget.
                # Invalid calls and repeated loads still count, preventing a useless loop.
                if call["name"] != "load_critic_skills":
                    count += 1

                try:
                    _validate_registered_tool(call)
                    validated = _parse_tool_query(call)
                    query = validated.text
                    evidence_type = validated.evidence_type
                    max_items = validated.max_items

                    # 本地文本检索使用 Retrieval Client，典故与出处查询使用证据服务。
                    if evidence_type == "critic_skill":
                        new_names = tuple(
                            name for name in validated.skill_names if name not in loaded_skills
                        )
                        if new_names:
                            result = load_critic_skills(new_names)
                            loaded_skills.update(new_names)
                        else:
                            result = {
                                "status": "already_loaded",
                                "message": "这些 Skill 已在本轮提供，请直接使用已有内容",
                                "skills": [],
                            }
                            count += 1
                    elif evidence_type == "web_search":
                        result = await deepseek_web_client.search(
                            query, source=validated.source
                        )
                        search_rows = result.get("results")
                        if not isinstance(search_rows, list):
                            raise DeepSeekWebError("联网搜索结果缺少列表")
                        permitted_urls.update(
                            entry["url"]
                            for entry in search_rows
                            if isinstance(entry, dict) and isinstance(entry.get("url"), str)
                        )
                    elif evidence_type == "moedict":
                        result = await classic_references_client.lookup_moedict(query)
                    elif evidence_type == "wikisource_search":
                        result = await classic_references_client.search_wikisource(query)
                        pages = result.get("results")
                        if not isinstance(pages, list):
                            raise ReferenceSourceError("维基文库搜索结果缺少列表")
                        permitted_pageids.update(
                            item["pageid"] for item in pages
                            if isinstance(item, dict) and type(item.get("pageid")) is int
                        )
                    elif evidence_type == "wikisource_page":
                        if validated.pageid not in permitted_pageids:
                            raise ValueError("只能读取本轮维基文库搜索命中的 pageid")
                        result = await classic_references_client.read_wikisource(
                            validated.pageid
                        )
                    elif evidence_type == "web_fetch":
                        if validated.url not in permitted_urls:
                            raise ValueError("只能读取本轮搜索结果中出现的公开网页 URL")
                        result = await deepseek_web_client.fetch(validated.url, permitted_urls)
                    elif evidence_type == "ci_meter":
                        # The user-selected/loaded poem is authoritative when the model omits content.
                        content = query or state["poem"].strip()
                        if not content or len(content) > 1200:
                            raise ValueError("词律分析正文必须为 1–1200 字的完整作品")
                        if validated.tune_name is None:
                            raise ValueError("缺少词牌名")
                        result = await cnkgraph_research_client.analyze_ci(
                            content=content, tune_name=validated.tune_name,
                        )
                    elif evidence_type == "classical_books":
                        result = await cnkgraph_research_client.search_books(query)
                    elif evidence_type == "ci_tune":
                        result = await cnkgraph_research_client.lookup_ci_tune(query)
                    elif evidence_type == "rhyme":
                        if validated.book is None:
                            raise ValueError("缺少韵书名")
                        result = await cnkgraph_research_client.lookup_rhyme(
                            validated.book,
                            validated.category_id,
                            validated.character,
                        )
                    elif evidence_type == "entities":
                        context = state.get("context")
                        content = query or state.get("selection") or state["poem"]
                        if not isinstance(content, str) or not 1 <= len(content.strip()) <= 450:
                            raise ValueError("实体标注正文必须为 1–450 字")
                        epoch = validated.epoch or (
                            context.dynasty if context and context.dynasty else "宋"
                        )
                        result = await cnkgraph_research_client.resolve_entities(
                            text=content.strip(), epoch=epoch,
                        )
                    elif evidence_type == "commentary":
                        document_result = await asyncio.to_thread(
                            document_retrieval.search,
                            state["question"],
                            extra_queries=(validated.text, *validated.extra_queries),
                        )
                        evidence_items = [
                            item.model_dump() for item in document_result.evidences[:max_items]
                        ]
                        all_evidences.extend(evidence_items)
                        result = {
                            "status": "ok" if evidence_items else "no_hit",
                            "query": state["question"],
                            "queries": document_result.queries,
                            "evidence_type": evidence_type,
                            "evidences": evidence_items,
                            "note": (
                                "检索结果是词话评论候选，不等于已完成论证。"
                                "引用观点时请明确书名、卷次与条目，区分原文和解释；"
                                "如果材料不足请说明，不能编造页码或原文。"
                            ),
                        }
                    elif evidence_type == "text_retrieval":
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
                        items: list[dict[str, object]] = []
                        for candidate in retrieval.candidates[:max_items]:
                            data: dict[str, object] = candidate.model_dump()
                            data["text"] = candidate.text[:800]
                            title = data.get("title")
                            if isinstance(title, str):
                                data["title"] = title[:200]
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
                        result, evidence_items = await _execute_evidence_query(
                            query=query,
                            evidence_type=evidence_type,
                            max_items=max_items,
                        )
                        all_evidences.extend(evidence_items)

                except (
                    ValueError,
                    KeyError,
                    TypeError,
                    CNKGraphError,
                    CNKGraphResearchError,
                    DeepSeekWebError,
                    ReferenceSourceError,
                    RetrievalClientError,
                    DocumentRetrievalError,
                ) as exc:
                    if call["name"] == "load_critic_skills":
                        count += 1
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
        "loaded_skills": sorted(loaded_skills),
        "evidences": [
            *(state.get("evidences") or []),
            *evidences,
        ],
    }


builder = StateGraph(AgentState)

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
