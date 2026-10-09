"""FastAPI surface for the long-lived Retrieval Serving runtime."""
from __future__ import annotations

import hmac
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from backend.retrieval.serving import RetrievalServingRuntime


class CurrentPoemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=12_000)
    title: str | None = Field(default=None, max_length=500)
    author: str | None = Field(default=None, max_length=200)
    dynasty: str | None = Field(default=None, max_length=100)


class RetrievalSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=120)
    top_k: int = Field(default=8, ge=1, le=20)
    current: CurrentPoemRequest


class RetrievalCandidateResponse(BaseModel):
    rank: int
    work_id: str
    text: str
    title: str | None
    author: str | None
    dynasty: str | None
    source_record_id: str | None
    chronology_status: str
    support_count: int


class RetrievalSearchResponse(BaseModel):
    status: Literal["ok", "no_hit"]
    query: str
    candidates: list[RetrievalCandidateResponse]


def create_app(
    runtime: RetrievalServingRuntime,
    *,
    api_token: str = "",
) -> FastAPI:
    app = FastAPI(
        title="Poeticus Text Retrieval Service",
        version="0.1.0",
    )

    def require_token(
        authorization: Annotated[str | None, Header()] = None,
    ) -> None:
        if not api_token:
            return
        expected = f"Bearer {api_token}"
        if authorization is None or not hmac.compare_digest(
            authorization,
            expected,
        ):
            raise HTTPException(status_code=401, detail="Unauthorized")

    @app.get("/health")
    def health() -> dict[str, str | object]:
        return {
            "status": "ok",
            "device": runtime.startup_profile.get("device"),
        }

    @app.get("/v1/retrieval/profile")
    def startup_profile(
        _: None = Depends(require_token),
    ) -> dict[str, object]:
        """Local/ops diagnostic; Agent client never needs this endpoint."""
        return runtime.startup_profile

    @app.post(
        "/v1/retrieval/search",
        response_model=RetrievalSearchResponse,
    )
    def search(
        request: RetrievalSearchRequest,
        _: None = Depends(require_token),
    ):
        try:
            result = runtime.search(
                request.text,
                current_text=request.current.text,
                current_author=request.current.author,
                target_dynasty=request.current.dynasty,
                final_top_k=request.top_k,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail=str(exc),
            ) from exc

        return RetrievalSearchResponse(
            status=result.status,
            query=result.query,
            candidates=[
                RetrievalCandidateResponse(
                    rank=item.rank,
                    work_id=item.work_id,
                    text=item.text,
                    title=item.title,
                    author=item.author,
                    dynasty=item.dynasty,
                    source_record_id=item.source_record_id,
                    chronology_status=item.chronology_status,
                    support_count=item.support_count,
                )
                for item in result.candidates
            ],
        )

    return app
