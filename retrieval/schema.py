"""文本检索实验的最小 Corpus / Chunk 数据契约。"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


ChunkPolicy = Literal["clause", "sentence", "clause_pair"]


class CorpusWork(BaseModel):
    """外部语料中的一篇作品。

    paragraphs 保留来源提供的段落数组；检索 chunk 由独立策略生成，
    不把某个外部仓库的 paragraph 直接等同于“句”。
    """

    model_config = ConfigDict(extra="forbid")

    work_id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    source_record_id: str = Field(min_length=1)
    source_locator: str | None = None
    author: str | None = None
    dynasty: str | None = None
    genre: str | None = None
    title: str | None = None
    rhythmic: str | None = None
    paragraphs: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def paragraphs_must_contain_text(self):
        if any(not paragraph.strip() for paragraph in self.paragraphs):
            raise ValueError("paragraphs 不能包含空文本")
        return self


class ChunkPosition(BaseModel):
    """chunk 对父作品正文位置的轻量定位。"""

    model_config = ConfigDict(extra="forbid")

    paragraph_index: int = Field(ge=0)
    unit_index: int = Field(ge=0)


class CorpusChunk(BaseModel):
    """可送入 Embedding / Retriever 的文本单元。"""

    model_config = ConfigDict(extra="forbid")

    chunk_id: str = Field(min_length=1)
    work_id: str = Field(min_length=1)
    policy: ChunkPolicy
    chunk_index: int = Field(ge=0)
    text: str = Field(min_length=1)
    positions: list[ChunkPosition] = Field(min_length=1)

    source: str = Field(min_length=1)
    source_record_id: str = Field(min_length=1)
    author: str | None = None
    dynasty: str | None = None
    genre: str | None = None
    title: str | None = None
    rhythmic: str | None = None
