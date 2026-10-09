"""独立 Text Retrieval Service 的 HTTP 客户端。

Web / Agent 进程不直接导入 FAISS、sentence-transformers 或本地检索资产；
这些依赖被隔离在 HTTP 服务之后。

Agent 只提供查询文本。当前作品的元数据由宿主程序补充，
避免模型自行编造用于排除自身命中的信息。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field

from backend.config import (
    TEXT_RETRIEVAL_API_TOKEN,
    TEXT_RETRIEVAL_BASE_URL,
    TEXT_RETRIEVAL_TIMEOUT_SECONDS,
)


class RetrievalClientError(RuntimeError):
    """远端 Retrieval Service 未能返回有效结果。"""


class RetrievalCandidate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    rank: int = Field(ge=1)
    work_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    title: str | None = None
    author: str | None = None
    dynasty: str | None = None
    source_record_id: str | None = None
    chronology_status: str | None = None
    support_count: int | None = Field(default=None, ge=1)


class RetrievalSearchResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: Literal["ok", "no_hit"]
    query: str = Field(min_length=1)
    candidates: list[RetrievalCandidate] = Field(default_factory=list)


@dataclass(frozen=True)
class CurrentPoem:
    text: str
    title: str | None = None
    author: str | None = None
    dynasty: str | None = None


class TextRetrievalClient:
    def __init__(
        self,
        *,
        base_url: str = TEXT_RETRIEVAL_BASE_URL,
        api_token: str = TEXT_RETRIEVAL_API_TOKEN,
        timeout_seconds: float = TEXT_RETRIEVAL_TIMEOUT_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self._base_url = base_url.strip().rstrip("/")
        self._api_token = api_token.strip()
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    @property
    def enabled(self) -> bool:
        return bool(self._base_url)

    async def search(
        self,
        *,
        text: str,
        current_poem: CurrentPoem,
        top_k: int = 8,
    ) -> RetrievalSearchResponse:
        query = text.strip()
        if not query:
            raise ValueError("Text Retrieval query 不能为空")
        if len(query) > 120:
            raise ValueError("Text Retrieval query 过长")
        if top_k <= 0:
            raise ValueError("top_k 必须为正整数")
        if not self.enabled:
            raise RetrievalClientError("Text Retrieval Service 尚未配置")

        headers = {}
        if self._api_token:
            headers["Authorization"] = f"Bearer {self._api_token}"

        payload = {
            "text": query,
            "top_k": top_k,
            "current": {
                "text": current_poem.text,
                "title": current_poem.title,
                "author": current_poem.author,
                "dynasty": current_poem.dynasty,
            },
        }

        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout_seconds,
                transport=self._transport,
                headers=headers,
            ) as client:
                response = await client.post(
                    "/v1/retrieval/search",
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise RetrievalClientError(
                "Text Retrieval Service 请求失败"
            ) from exc

        try:
            result = RetrievalSearchResponse.model_validate(data)
        except ValueError as exc:
            raise RetrievalClientError(
                "Text Retrieval Service 返回格式无效"
            ) from exc

        if result.query.strip() != query:
            raise RetrievalClientError(
                "Text Retrieval Service 返回的 query 与请求不一致"
            )
        if result.status == "no_hit" and result.candidates:
            raise RetrievalClientError(
                "Text Retrieval Service no_hit 却返回了候选"
            )
        if result.status == "ok" and not result.candidates:
            raise RetrievalClientError(
                "Text Retrieval Service ok 却没有候选"
            )

        ranks = [item.rank for item in result.candidates]
        if ranks != list(range(1, len(ranks) + 1)):
            raise RetrievalClientError(
                "Text Retrieval Service candidate rank 不连续"
            )

        return result


text_retrieval_client = TextRetrievalClient()
