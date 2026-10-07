"""Compact serving metadata for full-corpus Text Retrieval.

FAISS returns stable logical row ids. The serving path needs to recover the
corresponding Chunk / Work metadata without scanning multi-million-line JSONL
files on every request.

This module intentionally keeps the first implementation boring:

    FAISS global row
    -> SQLite primary-key lookup
    -> Chunk
    -> Work metadata

The database is a rebuildable serving artifact. Corpus JSONL remains the source
of truth.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Literal, Sequence

ChunkPolicy = Literal["sentence", "clause"]
_TABLES: dict[ChunkPolicy, str] = {
    "sentence": "sentence_chunks",
    "clause": "clause_chunks",
}


@dataclass(frozen=True)
class ChunkMetadata:
    global_row: int
    chunk_id: str
    work_id: str
    text: str
    start: int | None
    end: int | None


@dataclass(frozen=True)
class WorkMetadata:
    work_id: str
    title: str | None
    author: str | None
    dynasty: str | None
    source_record_id: str | None


def content_fingerprint(text: str) -> str:
    """High-confidence duplicate identity used by current-work exclusion."""
    normalized = "".join(text.split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _iter_jsonl(path: Path) -> Iterator[dict]:
    with path.open(encoding="utf-8") as stream:
        for line_no, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"{path} 第 {line_no} 行无法解析"
                ) from exc


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE works (
            work_id TEXT PRIMARY KEY,
            title TEXT,
            author TEXT,
            dynasty TEXT,
            source_record_id TEXT,
            content_fingerprint TEXT NOT NULL
        ) WITHOUT ROWID;

        CREATE INDEX works_author_fingerprint
        ON works(author, content_fingerprint);

        CREATE TABLE sentence_chunks (
            global_row INTEGER PRIMARY KEY,
            chunk_id TEXT NOT NULL,
            work_id TEXT NOT NULL,
            text TEXT NOT NULL,
            start INTEGER,
            end INTEGER
        );

        CREATE TABLE clause_chunks (
            global_row INTEGER PRIMARY KEY,
            chunk_id TEXT NOT NULL UNIQUE,
            work_id TEXT NOT NULL,
            text TEXT NOT NULL,
            start INTEGER,
            end INTEGER
        );
        """
    )


def _insert_works(
    connection: sqlite3.Connection,
    work_path: Path,
    *,
    batch_size: int,
) -> int:
    sql = """
        INSERT INTO works (
            work_id,
            title,
            author,
            dynasty,
            source_record_id,
            content_fingerprint
        ) VALUES (?, ?, ?, ?, ?, ?)
    """
    rows: list[tuple] = []
    count = 0

    for work in _iter_jsonl(work_path):
        work_id = work.get("work_id")
        content = work.get("content")
        if not isinstance(work_id, str) or not work_id:
            raise ValueError("Work JSONL 存在缺少有效 work_id 的记录")
        if not isinstance(content, str):
            raise ValueError(f"Work {work_id!r} 缺少有效 content")

        rows.append(
            (
                work_id,
                work.get("title"),
                work.get("author"),
                work.get("dynasty"),
                work.get("source_record_id"),
                content_fingerprint(content),
            )
        )
        if len(rows) >= batch_size:
            connection.executemany(sql, rows)
            count += len(rows)
            rows.clear()

    if rows:
        connection.executemany(sql, rows)
        count += len(rows)

    return count


def _insert_chunks(
    connection: sqlite3.Connection,
    chunk_path: Path,
    *,
    policy: ChunkPolicy,
    batch_size: int,
) -> int:
    table = _TABLES[policy]
    sql = f"""
        INSERT INTO {table} (
            global_row,
            chunk_id,
            work_id,
            text,
            start,
            end
        ) VALUES (?, ?, ?, ?, ?, ?)
    """
    rows: list[tuple] = []
    count = 0

    for global_row, chunk in enumerate(_iter_jsonl(chunk_path)):
        chunk_id = chunk.get("chunk_id")
        work_id = chunk.get("work_id")
        text = chunk.get("text")
        if not isinstance(chunk_id, str) or not chunk_id:
            raise ValueError(
                f"{policy} Chunk row {global_row} 缺少有效 chunk_id"
            )
        if not isinstance(work_id, str) or not work_id:
            raise ValueError(
                f"{policy} Chunk row {global_row} 缺少有效 work_id"
            )
        if not isinstance(text, str) or not text:
            raise ValueError(
                f"{policy} Chunk row {global_row} 缺少有效 text"
            )

        rows.append(
            (
                global_row,
                chunk_id,
                work_id,
                text,
                chunk.get("start"),
                chunk.get("end"),
            )
        )
        if len(rows) >= batch_size:
            connection.executemany(sql, rows)
            count += len(rows)
            rows.clear()

    if rows:
        connection.executemany(sql, rows)
        count += len(rows)

    return count


def build_metadata_store(
    *,
    work_path: Path,
    sentence_chunk_path: Path,
    clause_chunk_path: Path,
    output_path: Path,
    batch_size: int = 50_000,
    force: bool = False,
) -> dict:
    """Build one atomic SQLite serving artifact."""
    if batch_size <= 0:
        raise ValueError("batch_size 必须为正整数")

    work_path = work_path.expanduser().resolve()
    sentence_chunk_path = sentence_chunk_path.expanduser().resolve()
    clause_chunk_path = clause_chunk_path.expanduser().resolve()
    output_path = output_path.expanduser().resolve()

    for path in (work_path, sentence_chunk_path, clause_chunk_path):
        if not path.is_file():
            raise ValueError(f"输入文件不存在：{path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    if output_path.exists() and not force:
        raise ValueError(
            f"Metadata store 已存在：{output_path}；如需重建请传 force=True"
        )
    for path in (output_path, temp_path):
        if force and path.exists():
            path.unlink()
    if temp_path.exists():
        temp_path.unlink()

    import time

    started = time.perf_counter()
    connection = sqlite3.connect(temp_path)
    try:
        # This file is a rebuildable artifact and is not exposed until the
        # final atomic rename, so build-time durability is intentionally traded
        # for throughput.
        connection.execute("PRAGMA journal_mode = OFF")
        connection.execute("PRAGMA synchronous = OFF")
        connection.execute("PRAGMA temp_store = MEMORY")
        connection.execute("PRAGMA locking_mode = EXCLUSIVE")
        _create_schema(connection)

        work_count = _insert_works(
            connection,
            work_path,
            batch_size=batch_size,
        )
        connection.commit()

        sentence_count = _insert_chunks(
            connection,
            sentence_chunk_path,
            policy="sentence",
            batch_size=batch_size,
        )
        connection.commit()

        clause_count = _insert_chunks(
            connection,
            clause_chunk_path,
            policy="clause",
            batch_size=batch_size,
        )
        connection.commit()

        connection.execute("ANALYZE")
        connection.commit()
    finally:
        connection.close()

    temp_path.replace(output_path)
    elapsed = time.perf_counter() - started

    return {
        "status": "complete",
        "database": str(output_path),
        "database_bytes": output_path.stat().st_size,
        "database_gib": output_path.stat().st_size / (1024 ** 3),
        "works": work_count,
        "sentence_chunks": sentence_count,
        "clause_chunks": clause_count,
        "build_seconds": elapsed,
    }


class MetadataStore:
    """Read-only random lookup over the compact serving metadata artifact."""

    def __init__(self, path: Path):
        self.path = path.expanduser().resolve()
        if not self.path.is_file():
            raise ValueError(f"Metadata store 不存在：{self.path}")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.path.as_uri() + "?mode=ro",
            uri=True,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        return connection

    @staticmethod
    def _batched(values: Sequence[int], size: int = 500) -> Iterator[Sequence[int]]:
        for start in range(0, len(values), size):
            yield values[start:start + size]

    def read_chunks(
        self,
        policy: ChunkPolicy,
        row_ids: Iterable[int],
    ) -> dict[int, ChunkMetadata]:
        table = _TABLES[policy]
        wanted = sorted(set(row_ids))
        if not wanted:
            return {}
        if wanted[0] < 0:
            raise ValueError("global_row 不能为负数")

        found: dict[int, ChunkMetadata] = {}
        connection = self._connect()
        try:
            for batch in self._batched(wanted):
                placeholders = ",".join("?" for _ in batch)
                rows = connection.execute(
                    f"""
                    SELECT global_row, chunk_id, work_id, text, start, end
                    FROM {table}
                    WHERE global_row IN ({placeholders})
                    """,
                    list(batch),
                ).fetchall()
                for row in rows:
                    item = ChunkMetadata(
                        global_row=row["global_row"],
                        chunk_id=row["chunk_id"],
                        work_id=row["work_id"],
                        text=row["text"],
                        start=row["start"],
                        end=row["end"],
                    )
                    found[item.global_row] = item
        finally:
            connection.close()

        missing = sorted(set(wanted) - set(found))
        if missing:
            raise ValueError(
                f"{policy} metadata 找不到 row：{missing[:10]}"
            )
        return found

    def read_works(
        self,
        work_ids: Iterable[str],
    ) -> dict[str, WorkMetadata]:
        wanted = sorted(set(work_ids))
        if not wanted:
            return {}

        found: dict[str, WorkMetadata] = {}
        connection = self._connect()
        try:
            for start in range(0, len(wanted), 500):
                batch = wanted[start:start + 500]
                placeholders = ",".join("?" for _ in batch)
                rows = connection.execute(
                    f"""
                    SELECT
                        work_id,
                        title,
                        author,
                        dynasty,
                        source_record_id
                    FROM works
                    WHERE work_id IN ({placeholders})
                    """,
                    batch,
                ).fetchall()
                for row in rows:
                    item = WorkMetadata(
                        work_id=row["work_id"],
                        title=row["title"],
                        author=row["author"],
                        dynasty=row["dynasty"],
                        source_record_id=row["source_record_id"],
                    )
                    found[item.work_id] = item
        finally:
            connection.close()

        missing = sorted(set(wanted) - set(found))
        if missing:
            raise ValueError(
                f"Work metadata 找不到 work_id：{missing[:10]}"
            )
        return found

    def find_current_work_aliases(
        self,
        *,
        text: str,
        author: str | None,
    ) -> set[str]:
        if not author or not text.strip():
            return set()

        fingerprint = content_fingerprint(text)
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT work_id
                FROM works
                WHERE author = ? AND content_fingerprint = ?
                """,
                (author, fingerprint),
            ).fetchall()
        finally:
            connection.close()
        return {row["work_id"] for row in rows}
