"""聊天请求校验、普通响应与 SSE 流式接口。"""
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


class QuoteSelection(BaseModel):
    text: str = Field(max_length=CHAT_MAX_SELECTION_CHARS)
    start: int
    end: int


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    poem: str = Field(max_length=AI_MAX_POEM_CHARS)
    question: str = Field(max_length=CHAT_MAX_QUESTION_CHARS)
    selection: QuoteSelection | None = None
    context: PoemContext | None = None
    history: list[HistoryMessage] = Field(default_factory=list)


class ChatResponse(BaseModel):
    answer: str


def validate_chat_request(request: ChatRequest) -> None:
    """普通端点和流式端点共用校验；无效请求应在发出 SSE 头之前报 422。"""
    if not request.poem.strip():
        raise HTTPException(status_code=422, detail="诗歌原文不能为空")
    if not request.question.strip():
        raise HTTPException(status_code=422, detail="问题不能为空")

    selection = request.selection

    if selection is not None:
        if (
            selection.start < 0
            or selection.end > len(request.poem)
            or selection.start >= selection.end
            or request.poem[selection.start : selection.end] != selection.text
        ):
            raise HTTPException(status_code=422, detail="引用位置与原文不一致")

    history = request.history

    if len(history) % 2 != 0:
        raise HTTPException(
            status_code=422,
            detail="历史消息必须由完整的 user / assistant 轮次组成",
        )

    if len(history) > CHAT_MAX_HISTORY_MESSAGES:
        raise HTTPException(
            status_code=422,
            detail=f"历史消息最多保留 {CHAT_MAX_HISTORY_TURNS} 轮",
        )

    total_chars = 0

    for index, message in enumerate(history):
        expected_role = "user" if index % 2 == 0 else "assistant"

        if message.role != expected_role:
            raise HTTPException(
                status_code=422,
                detail="历史消息必须按 user / assistant 完整轮次排列",
            )

        if not message.content.strip():
            raise HTTPException(
                status_code=422,
                detail="历史消息内容不能为空",
            )

        if len(message.content) > CHAT_MAX_HISTORY_MESSAGE_CHARS:
            raise HTTPException(
                status_code=422,
                detail="单条历史消息过长",
            )

        total_chars += len(message.content)

    if total_chars > CHAT_MAX_HISTORY_TOTAL_CHARS:
        raise HTTPException(
            status_code=422,
            detail="历史消息总长度过长",
        )


def graph_input(request: ChatRequest) -> RouterState:
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


@router.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    """非流式聊天接口。"""
    validate_chat_request(request)
    try:
        result = graph.invoke(graph_input(request))
        answer = result.get("reply")
        if not answer:
            raise RuntimeError("工作流没有返回答案")
        return ChatResponse(answer=answer)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=502, detail="AI 生成暂时失败，请稍后再试") from exc


def sse(event: str, data: dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def stream_graph_reply(request: ChatRequest) -> Iterator[str]:
    """Graph 的 custom 事件承载正文 token，updates 事件承载节点结果。"""
    yield ": connected\n\n"

    received: list[str] = []
    separate_next_reply = False
    final_reply: str | None = None

    try:
        state = graph_input(request)
        state["stream_reply"] = True

        for mode, payload in graph.stream(
            state,
            stream_mode=["custom", "updates"],
        ):
            if mode == "custom":
                if not isinstance(payload, dict) or payload.get("type") != "token":
                    continue

                token = payload.get("text")
                if isinstance(token, str) and token:
                    if separate_next_reply:
                        yield sse("token", {"text": "\n\n"})
                        separate_next_reply = False

                    received.append(token)
                    yield sse("token", {"text": token})

            elif mode == "updates" and isinstance(payload, dict):
                agent_update = payload.get("agent")

                if isinstance(agent_update, dict) and agent_update.get("tool_calls"):
                    separate_next_reply = separate_next_reply or bool(received)
                    received.clear()

                for update in payload.values():
                    if isinstance(update, dict) and isinstance(
                        update.get("reply"), str
                    ):
                        final_reply = update["reply"]

        if not final_reply or not final_reply.strip():
            raise RuntimeError("工作流没有返回答案")

        if received:
            if "".join(received) != final_reply:
                raise RuntimeError("流式内容与工作流结果不一致")
        else:
            if separate_next_reply:
                yield sse("token", {"text": "\n\n"})

            yield sse("token", {"text": final_reply})

        yield sse("done", {})

    except (ValueError, RuntimeError) as exc:
        logger.warning("聊天流中断：%s", type(exc).__name__)
        yield sse("error", {"message": "生成中断，请稍后重试"})

    except Exception:
        logger.exception("聊天流发生未预期异常")
        yield sse("error", {"message": "生成过程中发生服务器错误"})


@router.post("/api/chat/stream")
def chat_stream(request: ChatRequest):
    validate_chat_request(request)
    return StreamingResponse(
        stream_graph_reply(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )
