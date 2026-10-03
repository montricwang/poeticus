"""Poeticus FastAPI：保留普通聊天端点，新增真实模型增量流。"""

import json
import logging
import os
from collections.abc import Iterator
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from main import PoemAnalysis, analyze_poem
from intent_router import graph, RouterState
from poem_context import PoemContext
from backend.corpus.router import router as corpus_router

logger = logging.getLogger(__name__)
app = FastAPI(
    title="Poeticus",
    version=os.getenv("POETICUS_VERSION", "0.1.0-dev"),
)
app.include_router(corpus_router)


@app.get("/health", tags=["service"])
def health():
    """Liveness only: no database, model API or external tools."""
    return {"status": "ok"}


@app.get("/api/info", tags=["service"])
def public_info():
    """Public product metadata; never expose runtime configuration."""
    return {
        "name": "Poeticus",
        "version": app.version,
        "repository": "https://github.com/montricwang/poeticus",
    }


class AnalyzeRequest(BaseModel):
    poem: str
    context: PoemContext | None = None


@app.post("/analyze", response_model=PoemAnalysis)
def analyze(request: AnalyzeRequest):
    if not request.poem.strip():
        raise HTTPException(status_code=422, detail="诗歌原文不能为空")
    try:
        return analyze_poem(request.poem, request.context)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


class QuoteSelection(BaseModel):
    text: str
    start: int
    end: int


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    poem: str
    question: str
    selection: QuoteSelection | None = None
    context: PoemContext | None = None
    history: list[HistoryMessage] = Field(default_factory=list)


class ChatResponse(BaseModel):
    answer: str


# v0.1 初始历史预算。
# 依据 2026-09-30 LangSmith 样本：
# 当前正常 AI 回答约 300–600 output tokens，
# 因此先保留最近 6 个完整 Turn。
# 字符限制主要作为异常输入的保险丝，后续根据真实多轮 Trace / Eval 调整。
MAX_HISTORY_TURNS = 6
MAX_HISTORY_MESSAGES = MAX_HISTORY_TURNS * 2
MAX_HISTORY_MESSAGE_CHARS = 4000
MAX_HISTORY_TOTAL_CHARS = 12000


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

    if len(history) > MAX_HISTORY_MESSAGES:
        raise HTTPException(
            status_code=422,
            detail=f"历史消息最多保留 {MAX_HISTORY_TURNS} 轮",
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

        if len(message.content) > MAX_HISTORY_MESSAGE_CHARS:
            raise HTTPException(
                status_code=422,
                detail="单条历史消息过长",
            )

        total_chars += len(message.content)

    if total_chars > MAX_HISTORY_TOTAL_CHARS:
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


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    """原有非流式接口不变，供旧客户端与回归测试使用。"""
    validate_chat_request(request)
    try:
        result = graph.invoke(graph_input(request))
        answer = result.get("reply")
        if not answer:
            raise RuntimeError("工作流没有返回答案")
        return ChatResponse(answer=answer)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def stream_graph_reply(request: ChatRequest) -> Iterator[str]:
    """Graph custom 事件承载 token，updates 事件承载节点结果。"""
    # 立即发送 SSE 注释，避免反向代理一直等待首个正文 Token。
    yield ": connected\n\n"

    # 只校验最近一轮 Agent 的正文；此前的工具调用说明不属于最终回答。
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
                        # 兼容现有前端：用空行分隔说明与正式回答。
                        # 分隔符不参与最终回答的完整性校验。
                        yield sse("token", {"text": "\n\n"})
                        separate_next_reply = False

                    received.append(token)
                    yield sse("token", {"text": token})

            elif mode == "updates" and isinstance(payload, dict):
                agent_update = payload.get("agent")

                if isinstance(agent_update, dict) and agent_update.get("tool_calls"):
                    # 这一轮的文字是工具调用前的说明。
                    # 下一轮重新记录正式回答。
                    separate_next_reply = separate_next_reply or bool(received)
                    received.clear()

                for update in payload.values():
                    if isinstance(update, dict) and isinstance(
                        update.get("reply"), str
                    ):
                        final_reply = update["reply"]

        if not final_reply or not final_reply.strip():
            raise RuntimeError("工作流没有返回答案")

        # 已收到正式回答的增量 Token 时，不再重复发送全文。
        if received:
            if "".join(received) != final_reply:
                raise RuntimeError("流式内容与工作流结果不一致")
        else:
            if separate_next_reply:
                yield sse("token", {"text": "\n\n"})

            yield sse("token", {"text": final_reply})

        yield sse("done", {})

    except (ValueError, RuntimeError) as exc:
        logger.warning("聊天流中断：%s", exc)
        yield sse("error", {"message": str(exc)})

    except Exception:
        logger.exception("聊天流发生未预期异常")
        yield sse("error", {"message": "生成过程中发生服务器错误"})


@app.post("/chat/stream")
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
