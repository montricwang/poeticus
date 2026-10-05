"""Assemble Poeticus FastAPI routes, middleware and built frontend."""
import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from backend.api.analysis import router as analysis_router, AnalyzeRequest, analyze
from backend.api.chat import router as chat_router, chat, chat_stream
from backend.api.service import router as service_router, health, public_info
from backend.corpus.router import router as corpus_router

# Export legacy names for callers still importing api.py.
from backend.ai.model import PoemAnalysis, analyze_poem
from backend.ai.graph import RouterState, graph
from backend.api.chat import (
    ChatRequest, ChatResponse, HistoryMessage, QuoteSelection,
    graph_input, sse, stream_graph_reply, validate_chat_request,
    MAX_HISTORY_TURNS, MAX_HISTORY_MESSAGES,
    MAX_HISTORY_MESSAGE_CHARS, MAX_HISTORY_TOTAL_CHARS,
)

app = FastAPI(
    title="Poeticus",
    version=os.getenv("POETICUS_VERSION", "0.1.0-dev"),
)
app.include_router(corpus_router)
app.include_router(service_router)
app.include_router(analysis_router)
app.include_router(chat_router)

# The static mount comes last to preserve all API and health routes.
if os.getenv("POETICUS_SERVE_FRONTEND", "").lower() in ("1", "true", "yes"):
    from backend.public_ai_guard import PublicAIGuard
    app.add_middleware(PublicAIGuard)
    frontend_dir = Path(__file__).resolve().parents[1] / "frontend" / "dist"
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")

if preview_password := os.getenv("POETICUS_PREVIEW_PASSWORD"):
    from backend.preview_guard import PreviewGuard
    app.add_middleware(
        PreviewGuard,
        username=os.getenv("POETICUS_PREVIEW_USER", "preview"),
        password=preview_password,
        allow_ai_post=os.getenv("POETICUS_PREVIEW_ALLOW_AI", "").lower() == "true",
    )
