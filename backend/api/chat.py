"""Poeticus 的聊天 HTTP 接口。

接收前端发送的作品、问题、选区和历史消息，校验请求数据，
再将其整理成 LangGraph 的输入状态，交给 Agent 生成回答。

提供两种响应方式：普通接口返回完整的 JSON 回答；流式接口
将生成的正文、完成状态和错误信息逐步返回给浏览器。
"""

import json
import logging
from collections.abc import Iterator
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.ai.context import PoemContext
from backend.ai.graph import RouterState, graph
from backend.config import (
    CHAT_MAX_HISTORY_MESSAGE_CHARS,
    CHAT_MAX_HISTORY_MESSAGES,
    CHAT_MAX_HISTORY_TOTAL_CHARS,
    CHAT_MAX_HISTORY_TURNS,
    AI_MAX_POEM_CHARS,
    CHAT_MAX_QUESTION_CHARS,
    CHAT_MAX_SELECTION_CHARS,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ===== 1. 请求与响应的数据模型 =====


class QuoteSelection(BaseModel):
    """用户引用的原文片段及其在完整诗文中的字符位置。"""

    text: str = Field(max_length=CHAT_MAX_SELECTION_CHARS)
    start: int
    end: int


class HistoryMessage(BaseModel):
    """一条历史对话消息；只允许 user 或 assistant 角色。"""

    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    """聊天请求的数据结构，包含作品、问题、选区、阅读上下文和历史消息。

    history 保存此前完整的用户与助手对话轮次。
    Pydantic 检查字段类型和长度，validate_chat_request 检查内容及关联约束。
    """

    poem: str = Field(max_length=AI_MAX_POEM_CHARS)
    question: str = Field(max_length=CHAT_MAX_QUESTION_CHARS)
    selection: QuoteSelection | None = None
    context: PoemContext | None = None
    history: list[HistoryMessage] = Field(default_factory=list)


class ChatResponse(BaseModel):
    """普通聊天接口返回的数据结构，以 answer 字段保存完整回答。"""

    answer: str


# ===== 2. 请求校验与状态转换 =====


def validate_chat_request(request: ChatRequest) -> None:
    """普通端点和流式端点共用校验；无效请求应在发出 SSE 头之前报 422。"""

    # --- 2.1 检查本轮正文与问题 ---

    if not request.poem.strip():
        raise HTTPException(status_code=422, detail="诗歌原文不能为空")
    if not request.question.strip():
        raise HTTPException(status_code=422, detail="问题不能为空")

    # --- 2.2 核对原文选区 ---

    selection = request.selection

    if selection is not None:
        # 选区起止位置必须有效，截取的原文必须与提交的选中文字一致。
        if (
            selection.start < 0
            or selection.end > len(request.poem)
            or selection.start >= selection.end
            or request.poem[selection.start : selection.end] != selection.text
        ):
            raise HTTPException(status_code=422, detail="引用位置与原文不一致")

    # --- 2.3 检查历史消息轮数 ---

    history = request.history

    # 一轮对话由一条 user 消息和一条 assistant 消息组成。
    if len(history) % 2 != 0:
        raise HTTPException(
            status_code=422,
            detail="历史消息必须由完整的 user / assistant 轮次组成",
        )

    # 检查历史消息数量是否超过上限。
    if len(history) > CHAT_MAX_HISTORY_MESSAGES:
        raise HTTPException(
            status_code=422,
            detail=f"历史消息最多保留 {CHAT_MAX_HISTORY_TURNS} 轮",
        )

    # --- 2.4 逐条校验历史消息，并累计总长度 ---

    total_chars = 0

    for index, message in enumerate(history):
        expected_role = "user" if index % 2 == 0 else "assistant"

        # 历史记录按 user、assistant 的顺序交替排列。
        if message.role != expected_role:
            raise HTTPException(
                status_code=422,
                detail="历史消息必须按 user / assistant 完整轮次排列",
            )

        # 每条历史消息都需要有实际内容。
        if not message.content.strip():
            raise HTTPException(
                status_code=422,
                detail="历史消息内容不能为空",
            )

        # 单条消息和全部历史消息分别有长度限制。
        if len(message.content) > CHAT_MAX_HISTORY_MESSAGE_CHARS:
            raise HTTPException(
                status_code=422,
                detail="单条历史消息过长",
            )

        total_chars += len(message.content)

    # 校验累计长度是否在允许范围内。
    if total_chars > CHAT_MAX_HISTORY_TOTAL_CHARS:
        raise HTTPException(
            status_code=422,
            detail="历史消息总长度过长",
        )


def graph_input(request: ChatRequest) -> RouterState:
    """将聊天请求中的作品、问题和对话上下文整理成 LangGraph 输入状态。"""

    # 保留本轮上下文，将历史消息转换成 Graph 使用的字典列表。
    return {
        "poem": request.poem,
        "question": request.question,
        "selection": request.selection.text if request.selection else None,
        "context": request.context,
        "history": [
            {
                "role": message.role,
                "content": message.content,
            }
            for message in request.history
        ],
    }


# ===== 3. 普通聊天接口 =====


@router.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    """执行一次聊天工作流，返回包含完整回答的 JSON 数据。"""

    validate_chat_request(request)
    try:
        # 同步运行整个工作流，取出最终回答并包装为响应模型。
        result = graph.invoke(graph_input(request))
        answer = result.get("reply")
        if not answer:
            raise RuntimeError("工作流没有返回答案")

        return ChatResponse(answer=answer)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(
            status_code=502, detail="AI 生成暂时失败，请稍后再试"
        ) from exc


# ===== 4. SSE 流式聊天 =====


def sse(event: str, data: dict[str, object]) -> str:
    """将事件名称和数据编码成一条 SSE 格式的文本。"""

    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def stream_graph_reply(request: ChatRequest) -> Iterator[str]:
    """执行 LangGraph，并逐条产出可以交给 StreamingResponse 的 SSE 文本。

    custom 事件提供正文 token，updates 事件提供节点结果；核对最终
    reply 与已收到的正式正文一致后，发出 done，失败时发出 error。
    """

    # --- 4.1 建立连接并初始化回答状态 ---

    yield ": connected\n\n"

    # received 记录当前正式回答的 token，工具调用时重新开始累计。

    received: list[str] = []
    separate_next_reply = False
    final_reply: str | None = None

    try:
        # --- 4.2 准备 Graph 的流式输入 ---

        state = graph_input(request)
        state["stream_reply"] = True

        # --- 4.3 处理 Graph 逐步返回的事件 ---

        for mode, payload in graph.stream(
            state,
            stream_mode=["custom", "updates"],
        ):
            if mode == "custom":
                # custom 事件里只处理正文 token，其他自定义事件跳过。
                if not isinstance(payload, dict) or payload.get("type") != "token":
                    continue

                token = payload.get("text")
                if isinstance(token, str) and token:
                    # 工具调用后的新回答开始时，用空行隔开前后两段文字。
                    if separate_next_reply:
                        yield sse("token", {"text": "\n\n"})
                        separate_next_reply = False

                    received.append(token)
                    yield sse("token", {"text": token})

            elif mode == "updates" and isinstance(payload, dict):
                # 读取 Agent 节点更新，判断本轮是否转入工具调用。
                agent_update = payload.get("agent")

                # Agent 决定调用工具时，将下一段文字视为新的正式回答。
                if isinstance(agent_update, dict) and agent_update.get("tool_calls"):
                    separate_next_reply = separate_next_reply or bool(received)
                    received.clear()

                # 收集各节点更新中的最终 reply，供结束时核对。
                for update in payload.values():
                    # 节点给出 reply 字段时，记录它作为最终结果。
                    if isinstance(update, dict) and isinstance(
                        update.get("reply"), str
                    ):
                        final_reply = update["reply"]

        # --- 4.4 核对并发送最终回答 ---

        if not final_reply or not final_reply.strip():
            raise RuntimeError("工作流没有返回答案")

        # 已流出的正文要与最终 reply 一致；若此前没有正文 token，
        # 则在此补发完整回答，再通知浏览器流已结束。

        if received:
            # 比对逐步发送的正文与 Graph 返回的完整回答。
            if "".join(received) != final_reply:
                raise RuntimeError("流式内容与工作流结果不一致")
        else:
            # 没有收到正文 token 时，直接将最终回答补发给浏览器。
            if separate_next_reply:
                yield sse("token", {"text": "\n\n"})

            yield sse("token", {"text": final_reply})

        yield sse("done", {})

    # 将生成过程中出现的错误转成 SSE error，供浏览器处理。
    except (ValueError, RuntimeError) as exc:
        logger.warning("聊天流中断：%s", type(exc).__name__)
        yield sse("error", {"message": "生成中断，请稍后重试"})

    except Exception:
        logger.exception("聊天流发生未预期异常")
        yield sse("error", {"message": "生成过程中发生服务器错误"})


@router.post("/api/chat/stream")
def chat_stream(request: ChatRequest):
    """校验流式聊天请求，返回持续消费 SSE 事件的 HTTP 响应。"""

    # 在响应开始前校验，确保非法请求仍以正常 HTTP 422 返回。
    validate_chat_request(request)

    # 交给 StreamingResponse 逐段发送，并关闭代理缓存与缓冲。
    return StreamingResponse(
        stream_graph_reply(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )
