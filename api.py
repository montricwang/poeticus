"""Poeticus FastAPI：保留普通聊天端点，新增真实模型增量流。"""

import json
import logging
from collections.abc import Iterator

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from main import PoemAnalysis, analyze_poem
from intent_router import graph
from poem_context import PoemContext

logger = logging.getLogger(__name__)
app = FastAPI(title="Poeticus")


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


class ChatRequest(BaseModel):
    poem: str
    question: str
    selection: QuoteSelection | None = None
    context: PoemContext | None = None


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


def graph_input(request: ChatRequest) -> dict:
    return {
        "poem": request.poem,
        "question": request.question,
        "selection": request.selection.text if request.selection else None,
        "context": request.context,
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
    """Graph custom 事件承载 token，updates 事件承载最终回复与静态分支。"""
    # 立即发送 SSE 注释，避免反向代理一直等待首个正文 Token。
    yield ": connected\n\n"

    received: list[str] = []
    final_reply: str | None = None
    try:
        state = {**graph_input(request), "stream_reply": True}
        for mode, payload in graph.stream(state, stream_mode=["custom", "updates"]):
            if mode == "custom":
                if not isinstance(payload, dict) or payload.get("type") != "token":
                    continue
                token = payload.get("text")
                if isinstance(token, str) and token:
                    received.append(token)
                    yield sse("token", {"text": token})
            elif mode == "updates" and isinstance(payload, dict):
                for update in payload.values():
                    if isinstance(update, dict) and isinstance(
                        update.get("reply"), str
                    ):
                        final_reply = update["reply"]

        if not final_reply or not final_reply.strip():
            raise RuntimeError("工作流没有返回答案")

        # source_lookup / clarification 仍是静态 Graph 节点，发送一次即可。
        # 直接生成分支已经发送过 Token，不重复推送全文。
        if received:
            if "".join(received) != final_reply:
                raise RuntimeError("流式内容与工作流结果不一致")
        else:
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
