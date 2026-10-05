"""Public health, metadata and browser-safe capability routes."""
from fastapi import APIRouter, Request

from backend.config import (
    CHAT_MAX_HISTORY_TURNS,
    CHAT_MAX_QUESTION_CHARS,
    CHAT_MAX_SELECTION_CHARS,
)

router = APIRouter()


@router.get("/health", tags=["service"])
def health():
    """Liveness only: no database, model API or external tools."""
    return {"status": "ok"}


@router.get("/api/info", tags=["service"])
def public_info(request: Request):
    """Public product metadata; never expose runtime configuration."""
    return {
        "name": "Poeticus",
        "version": request.app.version,
        "repository": "https://github.com/montricwang/poeticus",
    }


@router.get("/api/capabilities", tags=["service"])
@router.get("/capabilities", include_in_schema=False)
def public_capabilities():
    """Expose only browser-relevant API contract limits, never secrets."""
    return {
        "chat": {
            "maxHistoryTurns": CHAT_MAX_HISTORY_TURNS,
            "maxQuestionChars": CHAT_MAX_QUESTION_CHARS,
            "maxSelectionChars": CHAT_MAX_SELECTION_CHARS,
        }
    }
