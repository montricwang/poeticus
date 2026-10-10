"""组装 Poeticus 的 FastAPI 路由、中间件与构建后的前端。"""
import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from backend.api.analysis import router as analysis_router
from backend.api.chat import router as chat_router
from backend.api.service import router as service_router
from backend.corpus.router import router as corpus_router


app = FastAPI(
    title="Poeticus",
    version=os.getenv("POETICUS_VERSION", "0.4.0-dev"),
)
app.include_router(corpus_router)
app.include_router(service_router)
app.include_router(analysis_router)
app.include_router(chat_router)

# 静态站点最后挂载，避免覆盖 API 与健康检查路由。
if os.getenv("POETICUS_SERVE_FRONTEND", "").lower() in ("1", "true", "yes"):
    from backend.public_ai_guard import PublicAIGuard
    app.add_middleware(PublicAIGuard)
    frontend_dir = Path(__file__).resolve().parents[1] / "frontend" / "dist"
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")

