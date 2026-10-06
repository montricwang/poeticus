"""外部古典诗词语料的标准化与 chunk 生成。"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from retrieval.schema import ChunkPolicy, ChunkPosition, CorpusChunk, CorpusWork


CLAUSE_BOUNDARY = re.compile(r"(?<=[，。！？；!?;])")
SENTENCE_BOUNDARY = re.compile(r"(?<=[。！？!?])")


@dataclass(frozen=True)
class _Unit:
    text: str
    paragraph_index: int
    unit_index: int


def stable_work_id(source: str, source_record_id: str) -> str:
    """用 provider + provider record id 生成稳定且短的内部 work id。"""

    digest = hashlib.sha256(
        f"{source}\0{source_record_id}".encode("utf-8")
    ).hexdigest()[:24]
    return f"{source}:{digest}"


def _clean_optional_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _split_paragraph(
    paragraph: str,
    *,
    paragraph_index: int,
    boundary: re.Pattern[str],
) -> list[_Unit]:
    parts = [part.strip() for part in boundary.split(paragraph) if part.strip()]
    return [
        _Unit(
            text=part,
            paragraph_index=paragraph_index,
            unit_index=unit_index,
        )
        for unit_index, part in enumerate(parts)
    ]


def _units_for_policy(work: CorpusWork, policy: ChunkPolicy) -> list[_Unit]:
    boundary = SENTENCE_BOUNDARY if policy == "sentence" else CLAUSE_BOUNDARY
    units: list[_Unit] = []
    for paragraph_index, paragraph in enumerate(work.paragraphs):
        units.extend(
            _split_paragraph(
                paragraph,
                paragraph_index=paragraph_index,
                boundary=boundary,
            )
        )
    return units


def build_chunks(work: CorpusWork, policy: ChunkPolicy) -> list[CorpusChunk]:
    """按指定策略为一篇作品生成可检索 chunk。

    clause_pair 使用相邻 clause 的滑动窗口；单 clause 作品仍保留一个 chunk。
    """

    units = _units_for_policy(work, policy)
    if not units:
        raise ValueError(f"{work.work_id}: 没有可生成 chunk 的正文")

    if policy == "clause_pair":
        if len(units) == 1:
            groups = [[units[0]]]
        else:
            groups = [
                [units[index], units[index + 1]]
                for index in range(len(units) - 1)
            ]
    else:
        groups = [[unit] for unit in units]

    chunks = []
    for chunk_index, group in enumerate(groups):
        text = "".join(unit.text for unit in group)
        chunks.append(
            CorpusChunk(
                chunk_id=f"{work.work_id}:{policy}:{chunk_index}",
                work_id=work.work_id,
                policy=policy,
                chunk_index=chunk_index,
                text=text,
                positions=[
                    ChunkPosition(
                        paragraph_index=unit.paragraph_index,
                        unit_index=unit.unit_index,
                    )
                    for unit in group
                ],
                source=work.source,
                source_record_id=work.source_record_id,
                author=work.author,
                dynasty=work.dynasty,
                genre=work.genre,
                title=work.title,
                rhythmic=work.rhythmic,
            )
        )
    return chunks


def _load_chinese_poetry_file(
    path: Path,
    *,
    dynasty: str | None,
    genre: str | None,
) -> list[CorpusWork]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"{path.name}: chinese-poetry JSON 顶层必须是数组")

    works = []
    for record_index, record in enumerate(payload):
        if not isinstance(record, dict):
            raise ValueError(f"{path.name}#{record_index}: 作品记录不是对象")

        raw_paragraphs = record.get("paragraphs")
        if not isinstance(raw_paragraphs, list):
            raise ValueError(
                f"{path.name}#{record_index}: paragraphs 不是数组"
            )

        paragraphs = [
            paragraph.strip()
            for paragraph in raw_paragraphs
            if isinstance(paragraph, str) and paragraph.strip()
        ]
        if not paragraphs:
            raise ValueError(
                f"{path.name}#{record_index}: 没有有效正文"
            )

        raw_id = record.get("id")
        source_record_id = (
            raw_id.strip()
            if isinstance(raw_id, str) and raw_id.strip()
            else f"{path.name}#{record_index}"
        )
        source_locator = f"{path.name}#{record_index}"

        works.append(
            CorpusWork(
                work_id=stable_work_id("chinese-poetry", source_record_id),
                source="chinese-poetry",
                source_record_id=source_record_id,
                source_locator=source_locator,
                author=_clean_optional_string(record.get("author")),
                dynasty=_clean_optional_string(dynasty),
                genre=_clean_optional_string(genre),
                title=_clean_optional_string(record.get("title")),
                rhythmic=_clean_optional_string(record.get("rhythmic")),
                paragraphs=paragraphs,
            )
        )

    return works


def load_chinese_poetry(
    path: Path,
    *,
    dynasty: str | None = None,
    genre: str | None = None,
    file_pattern: str = "*.json",
) -> list[CorpusWork]:
    """读取 chinese-poetry 的一个 JSON 文件或某目录下的顶层 JSON 文件。

    目录模式必须显式给出合适的 file_pattern（例如 poet.tang.*.json），
    避免把 authors.*.json 等不同结构的数据混进作品语料。
    """

    if path.is_file():
        files = [path]
    elif path.is_dir():
        files = sorted(path.glob(file_pattern))
    else:
        raise FileNotFoundError(path)

    if not files:
        raise ValueError(f"{path}: 没有找到 JSON 文件")

    works: list[CorpusWork] = []
    seen_work_ids: set[str] = set()

    for file_path in files:
        for work in _load_chinese_poetry_file(
            file_path,
            dynasty=dynasty,
            genre=genre,
        ):
            if work.work_id in seen_work_ids:
                raise ValueError(
                    f"重复来源记录：{work.source}:{work.source_record_id}"
                )
            seen_work_ids.add(work.work_id)
            works.append(work)

    return works


def write_jsonl(items: Iterable[CorpusWork | CorpusChunk], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for item in items:
            handle.write(item.model_dump_json() + "\n")
