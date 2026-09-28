from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from main import analyze_poem, PoemAnalysis


app = FastAPI(title="Poeticus")


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
