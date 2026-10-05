"""整首赏析 HTTP 接口。"""
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from backend.ai.model import PoemAnalysis, analyze_poem
from backend.ai.context import PoemContext
from backend.config import AI_MAX_POEM_CHARS

logger = logging.getLogger(__name__)
router = APIRouter()

class AnalyzeRequest(BaseModel):
    poem: str = Field(max_length=AI_MAX_POEM_CHARS)
    context: PoemContext | None = None


@router.post("/api/analyze", response_model=PoemAnalysis)
@router.post("/analyze", response_model=PoemAnalysis)
def analyze(request: AnalyzeRequest):
    if not request.poem.strip():
        raise HTTPException(status_code=422, detail="诗歌原文不能为空")
    try:
        return analyze_poem(request.poem, request.context)
    except (ValueError, RuntimeError) as exc:
        # 这里只记录运维诊断所需的异常类型；绝不记录原文、模型响应、
        # 上游错误详情或任何凭据。
        logger.warning(
            "analysis_failed type=%s upstream_type=%s",
            type(exc).__name__,
            type(exc.__cause__).__name__ if exc.__cause__ else "none",
        )
        raise HTTPException(status_code=502, detail="AI 生成暂时失败，请稍后再试") from exc
