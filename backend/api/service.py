"""公开健康检查、产品元数据与浏览器可见能力接口。"""
from fastapi import APIRouter, Request

from backend.config import (
    CHAT_MAX_HISTORY_TURNS,
    CHAT_MAX_QUESTION_CHARS,
    CHAT_MAX_SELECTION_CHARS,
)

router = APIRouter()


@router.get("/health", tags=["service"])
def health():
    """只做存活检查，不访问数据库、模型 API 或外部工具。"""
    return {"status": "ok"}


@router.get("/api/info", tags=["service"])
def public_info(request: Request):
    """公开产品元数据，不暴露运行时配置。"""
    return {
        "name": "Poeticus",
        "version": request.app.version,
        "repository": "https://github.com/montricwang/poeticus",
    }


@router.get("/api/capabilities", tags=["service"])
def public_capabilities():
    """只公开浏览器需要遵守的 API 契约限制，不公开秘密配置。"""
    return {
        "chat": {
            "maxHistoryTurns": CHAT_MAX_HISTORY_TURNS,
            "maxQuestionChars": CHAT_MAX_QUESTION_CHARS,
            "maxSelectionChars": CHAT_MAX_SELECTION_CHARS,
        }
    }
