"""HTTP contract for the PostgreSQL poem catalog; no AI or frontend logic."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from psycopg import Connection

from .connection import get_connection
from .repository import get_poem, list_poems

router = APIRouter(prefix="/api/poems", tags=["poems"])


class PoemSummary(BaseModel):
    id: UUID
    source_order: int
    collection: str
    author: str | None
    tune: str | None
    title: str | None
    yusheng: str | None
    incipit: str
    review_status: str


class PoemPage(BaseModel):
    items: list[PoemSummary]
    total: int
    limit: int
    offset: int


class PoemDetail(BaseModel):
    id: UUID
    source_order: int
    collection: str
    author: str | None
    tune: str | None
    title: str | None
    yusheng: str | None
    body_segments: list[str]
    prefaces: list[str]
    review_status: str
    text_version: int


@router.get("", response_model=PoemPage)
def catalog(
    author: str | None = Query(default=None, max_length=80),
    tune: str | None = Query(default=None, max_length=80),
    q: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    conn: Connection = Depends(get_connection),
):
    """Query params -> filtered page ordered by the original book sequence."""
    records, total = list_poems(
        conn,
        author=author.strip() or None if author is not None else None,
        tune=tune.strip() or None if tune is not None else None,
        q=q.strip() or None if q is not None else None,
        limit=limit, offset=offset,
    )
    return PoemPage(items=records, total=total, limit=limit, offset=offset)


@router.get("/{poem_id}", response_model=PoemDetail)
def detail(poem_id: UUID, conn: Connection = Depends(get_connection)):
    """UUID -> reader-facing text; never return source evidence."""
    record = get_poem(conn, poem_id)
    if record is None:
        raise HTTPException(status_code=404, detail="未找到该作品")
    return PoemDetail.model_validate(record)
