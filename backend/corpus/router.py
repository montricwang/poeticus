"""PostgreSQL 作品目录的 HTTP 契约，不包含 AI 或前端逻辑。"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from psycopg import Connection
from psycopg.rows import DictRow

from .connection import get_connection
from .repository import get_poem, get_poem_neighbors, list_poems

router = APIRouter(prefix="/api/poems", tags=["poems"])


def _clean_filter(value: str | None) -> str | None:
    """去掉筛选值首尾空白；纯空白与未提供都视为无筛选。"""
    if value is None:
        return None
    return value.strip() or None


class PoemSummary(BaseModel):
    id: UUID
    source_order: int
    collection: str
    author: str | None
    cipai: str | None
    title: str | None
    yusheng_title: str | None
    incipit: str
    review_status: str


class PoemPage(BaseModel):
    items: list[PoemSummary]
    total: int
    limit: int
    offset: int


class PoemNeighbors(BaseModel):
    previous_id: UUID | None
    next_id: UUID | None


class PoemDetail(BaseModel):
    id: UUID
    source_order: int
    collection: str
    author: str | None
    cipai: str | None
    title: str | None
    yusheng_title: str | None
    body_segments: list[str]
    prefaces: list[str]
    review_status: str
    text_version: int


@router.get("", response_model=PoemPage)
def catalog(
    author: str | None = Query(default=None, max_length=80),
    cipai: str | None = Query(default=None, max_length=80),
    q: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    conn: Connection[DictRow] = Depends(get_connection),
):
    """按查询参数筛选，并按原书顺序返回分页结果。"""
    records, total = list_poems(
        conn,
        author=_clean_filter(author),
        cipai=_clean_filter(cipai),
        q=_clean_filter(q),
        limit=limit, offset=offset,
    )
    return PoemPage(
        items=[PoemSummary.model_validate(record) for record in records],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{poem_id}", response_model=PoemDetail)
def detail(poem_id: UUID, conn: Connection[DictRow] = Depends(get_connection)):
    """按 UUID 返回阅读端正文，绝不返回私人来源证据。"""
    record = get_poem(conn, poem_id)
    if record is None:
        raise HTTPException(status_code=404, detail="未找到该作品")
    return PoemDetail.model_validate(record)


@router.get("/{poem_id}/neighbors", response_model=PoemNeighbors)
def neighbors(poem_id: UUID, conn: Connection[DictRow] = Depends(get_connection)):
    """按数据库原书顺序阅读上一首、下一首；不依赖目录当前页。"""
    record = get_poem_neighbors(conn, poem_id)
    if record is None:
        raise HTTPException(status_code=404, detail="未找到该作品")
    return PoemNeighbors.model_validate(record)
