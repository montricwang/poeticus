"""外部古典诗词语料的最小统一契约与切块策略。"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Iterable, Literal

from pydantic import BaseModel, ConfigDict, Field

from evals.retrieval import PoetryCorpusRecord


ChunkPolicy = Literal["clause", "sentence", "clause_pair"]

_CLAUSE_SPLIT_RE = re.compile(r"([，。！？；])")
_SENTENCE_SPLIT_RE = re.compile(r"([。！？])")


class CorpusWork(BaseModel):
    """Retrieval corpus 中的父作品。"""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_.:-]+$")
    author: str | None = None
    dynasty: str | None = None
    title: str | None = None
    full_text: str = Field(min_length=1)
    source: str = Field(min_length=1)
    source_record_id: str = Field(min_length=1)


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\u241f".join(parts).encode("utf-8")).hexdigest()[:20]
    return f"{prefix}.{digest}"


def _split_preserving_terminal(text: str, pattern: re.Pattern[str]) -> list[str]:
    pieces = pattern.split(text.strip())
    chunks: list[str] = []
    current = ""

    for piece in pieces:
        if not piece:
            continue
        if pattern.fullmatch(piece):
            current += piece
            if current.strip():
                chunks.append(current.strip())
            current = ""
        else:
            if current and not current.endswith(tuple("，。！？；")):
                current += piece
            else:
                current = piece

    if current.strip():
        chunks.append(current.strip())
    return chunks


def split_text(text: str, policy: ChunkPolicy) -> list[str]:
    """按 Retrieval 实验策略切分一段文本。"""

    if policy == "clause":
        return _split_preserving_terminal(text, _CLAUSE_SPLIT_RE)

    if policy == "sentence":
        return _split_preserving_terminal(text, _SENTENCE_SPLIT_RE)

    if policy == "clause_pair":
        clauses = _split_preserving_terminal(text, _CLAUSE_SPLIT_RE)
        if len(clauses) <= 1:
            return clauses
        return [
            f"{clauses[index]}{clauses[index + 1]}"
            for index in range(len(clauses) - 1)
        ]

    raise ValueError(f"未知 chunk policy: {policy}")


def chunks_for_work(work: CorpusWork, policy: ChunkPolicy) -> list[PoetryCorpusRecord]:
    texts = split_text(work.full_text, policy)
    return [
        PoetryCorpusRecord(
            id=_stable_id("chunk", work.id, policy, str(position), text),
            work_id=work.id,
            text=text,
            author=work.author,
            dynasty=work.dynasty,
            title=work.title,
            source=work.source,
            source_record_id=work.source_record_id,
            chunk_type=policy,
            position=position,
        )
        for position, text in enumerate(texts)
    ]


def parse_chinese_poetry_records(
    payload: object,
    *,
    source: str,
    source_path: str,
    dynasty: str | None,
) -> list[CorpusWork]:
    """把 chinese-poetry 常见 JSON 列表适配成 CorpusWork。"""

    if not isinstance(payload, list):
        raise ValueError("chinese-poetry 输入必须是 JSON array")

    works: list[CorpusWork] = []
    for index, raw in enumerate(payload):
        if not isinstance(raw, dict):
            raise ValueError(f"第 {index} 条记录不是 object")

        paragraphs = raw.get("paragraphs")
        if not isinstance(paragraphs, list) or not paragraphs:
            continue

        clean_paragraphs = [
            paragraph.strip()
            for paragraph in paragraphs
            if isinstance(paragraph, str) and paragraph.strip()
        ]
        if not clean_paragraphs:
            continue

        author = raw.get("author")
        if not isinstance(author, str):
            author = None

        title = raw.get("title")
        if not isinstance(title, str) or not title.strip():
            rhythmic = raw.get("rhythmic")
            title = rhythmic.strip() if isinstance(rhythmic, str) and rhythmic.strip() else None
        elif title:
            title = title.strip()

        source_record_id = raw.get("id")
        if not isinstance(source_record_id, str) or not source_record_id.strip():
            source_record_id = f"{source_path}#{index}"

        full_text = "\n".join(clean_paragraphs)
        work_id = _stable_id(
            "work",
            source,
            source_record_id,
            author or "",
            title or "",
            full_text,
        )

        works.append(
            CorpusWork(
                id=work_id,
                author=author,
                dynasty=dynasty,
                title=title,
                full_text=full_text,
                source=source,
                source_record_id=source_record_id,
            )
        )

    if not works:
        raise ValueError("输入中没有可用诗词作品")
    return works


def load_chinese_poetry_file(
    path: Path,
    *,
    source: str = "chinese-poetry/chinese-poetry",
    dynasty: str | None = None,
) -> list[CorpusWork]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return parse_chinese_poetry_records(
        payload,
        source=source,
        source_path=path.name,
        dynasty=dynasty,
    )


def write_jsonl(records: Iterable[BaseModel], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(record.model_dump_json() + "\n")
