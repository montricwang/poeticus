from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from main import PoemAnalysis, analyze_poem
from intent_router import graph

app = FastAPI(title="Poeticus")


# 整首赏析


class AnalyzeRequest(BaseModel):
    poem: str


@app.post("/analyze", response_model=PoemAnalysis)
def analyze(request: AnalyzeRequest):
    if not request.poem.strip():
        raise HTTPException(
            status_code=422,
            detail="诗歌原文不能为空",
        )

    try:
        return analyze_poem(request.poem)

    except (ValueError, RuntimeError) as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc


# 诗歌对话


class QuoteSelection(BaseModel):
    text: str
    start: int
    end: int


class ChatRequest(BaseModel):
    poem: str
    question: str
    selection: QuoteSelection | None = None


class ChatResponse(BaseModel):
    answer: str


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    if not request.poem.strip():
        raise HTTPException(
            status_code=422,
            detail="诗歌原文不能为空",
        )

    if not request.question.strip():
        raise HTTPException(
            status_code=422,
            detail="问题不能为空",
        )

    selection = request.selection

    if selection is not None:
        if (
            selection.start < 0
            or selection.end > len(request.poem)
            or selection.start >= selection.end
            or request.poem[selection.start : selection.end] != selection.text
        ):
            raise HTTPException(
                status_code=422,
                detail="引用位置与原文不一致",
            )

    try:
        result = graph.invoke(
            {
                "poem": request.poem,
                "question": request.question,
                "selection": selection.text if selection else None,
            }
        )

        answer = result.get("reply")

        if not answer:
            raise RuntimeError("工作流没有返回答案")

        return ChatResponse(answer=answer)

    except (ValueError, RuntimeError) as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc
