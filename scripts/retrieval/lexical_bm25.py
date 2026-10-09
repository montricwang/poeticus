"""Character n-gram + BM25 lexical retrieval baseline.

This module builds a local SQLite FTS5 artifact over Werneror Chunk JSONL and
searches it with BM25. The text representation and ranking layers stay
explicit:

    text -> character n-grams -> FTS5 inverted index -> BM25 ranking

The index is a rebuildable retrieval artifact, not the authoritative corpus.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from backend.data_paths import RETRIEVAL_CORPUS_ROOT
from typing import Iterable, Iterator, TypedDict

from pydantic import ConfigDict, TypeAdapter, with_config

from backend.retrieval.chronology import candidate_prior_dynasties

from scripts.retrieval.exact_search import (
    DEFAULT_DATA_ROOT,
    DEFAULT_TOP_K,
    sha256_file,
)

DEFAULT_INDEX_ROOT = DEFAULT_DATA_ROOT / "lexical"
DEFAULT_WORKS = RETRIEVAL_CORPUS_ROOT / "werneror_works.jsonl"
CHUNK_PATHS = {
    "sentence": RETRIEVAL_CORPUS_ROOT / "werneror_chunks_sentence.jsonl",
    "clause": RETRIEVAL_CORPUS_ROOT / "werneror_chunks_clause.jsonl",
}
DEFAULT_MIN_N = 2
DEFAULT_MAX_N = 3
DEFAULT_BATCH_SIZE = 10_000


@with_config(ConfigDict(extra="allow"))
class BM25Manifest(TypedDict):
    status: str
    engine: str
    ranking: str
    term_representation: str
    chunk_policy: str
    min_n: int
    max_n: int
    works: int
    chunks: int
    max_chunks: int | None
    sampled_chunks_seen: int | None
    database_bytes: int
    database_mib: float
    build_elapsed_seconds: float
    chunks_per_second: float | None
    work_path: str
    work_sha256: str
    chunk_path: str
    chunk_sha256: str
    database: str
    created_at: str


class BM25Chunk(TypedDict):
    chunk_id: str
    text: str
    start: int | None
    end: int | None


class BM25Work(TypedDict):
    work_id: str
    title: str | None
    author: str | None
    dynasty: str | None
    source_record_id: str | None


class BM25RankedHit(TypedDict):
    rank: int
    bm25_score: float
    global_row: int
    chunk: BM25Chunk
    work: BM25Work


class BM25SearchResult(TypedDict):
    query: str
    engine: str
    ranking_method: str
    term_representation: str
    chunk_policy: str
    ngram_range: list[int]
    top_k: int
    chronology_filter: dict[str, object] | None
    ranking: list[BM25RankedHit]
    probes: list[BM25RankedHit]
    note: str


_MANIFEST_ADAPTER = TypeAdapter(BM25Manifest)
EXPECTED_CHUNKS = {
    "sentence": 4_822_054,
    "clause": 9_425_173,
}


def iter_character_runs(text: str) -> Iterator[str]:
    """Yield alphanumeric Unicode runs; punctuation acts as a boundary."""
    current: list[str] = []
    for char in text:
        if char.isalnum():
            current.append(char)
            continue
        if current:
            yield "".join(current)
            current = []
    if current:
        yield "".join(current)


def character_ngrams(
    text: str,
    *,
    min_n: int = DEFAULT_MIN_N,
    max_n: int = DEFAULT_MAX_N,
) -> list[str]:
    if min_n <= 0 or max_n < min_n:
        raise ValueError("n-gram 范围必须满足 0 < min_n <= max_n")

    grams: list[str] = []
    for run in iter_character_runs(text):
        for n in range(min_n, max_n + 1):
            if len(run) < n:
                continue
            grams.extend(run[index:index + n] for index in range(len(run) - n + 1))
    return grams


def unique_in_order(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(values))


def build_match_query(
    query: str,
    *,
    min_n: int = DEFAULT_MIN_N,
    max_n: int = DEFAULT_MAX_N,
) -> str:
    grams = unique_in_order(character_ngrams(query, min_n=min_n, max_n=max_n))
    if not grams:
        raise ValueError(
            f"Query 在 {min_n}-{max_n} gram 规则下没有可检索词项"
        )
    escaped = [gram.replace('"', '""') for gram in grams]
    return " OR ".join(f'"{gram}"' for gram in escaped)


def default_output_dir(
    chunk_policy: str,
    *,
    min_n: int = DEFAULT_MIN_N,
    max_n: int = DEFAULT_MAX_N,
) -> Path:
    if chunk_policy not in CHUNK_PATHS:
        raise ValueError(f"未知 chunk policy：{chunk_policy!r}")
    return DEFAULT_INDEX_ROOT / f"bm25_{chunk_policy}_{min_n}_{max_n}"


def _check_fts5(connection: sqlite3.Connection) -> None:
    try:
        connection.execute("CREATE VIRTUAL TABLE temp.fts5_check USING fts5(text)")
        connection.execute("DROP TABLE temp.fts5_check")
    except sqlite3.OperationalError as exc:
        raise RuntimeError(
            "当前 Python SQLite 未启用 FTS5，不能建立 BM25 lexical index"
        ) from exc


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        PRAGMA foreign_keys = ON;

        CREATE TABLE works (
            work_id TEXT PRIMARY KEY,
            title TEXT,
            author TEXT,
            dynasty TEXT,
            source_record_id TEXT
        );

        CREATE TABLE chunks (
            rowid INTEGER PRIMARY KEY,
            chunk_id TEXT NOT NULL UNIQUE,
            work_id TEXT NOT NULL REFERENCES works(work_id),
            text TEXT NOT NULL,
            start INTEGER,
            end INTEGER
        );

        CREATE VIRTUAL TABLE chunk_fts USING fts5(
            grams,
            content='',
            tokenize='unicode61'
        );
        """
    )


def _read_jsonl(path: Path) -> Iterator[dict[str, object]]:
    with path.open(encoding="utf-8") as stream:
        for line_no, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                if not isinstance(record, dict):
                    raise ValueError(f"{path} 第 {line_no} 行必须是 JSON 对象")
                yield record
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path} 第 {line_no} 行无法解析") from exc


def collect_chunk_work_ids(
    chunk_path: Path,
    *,
    max_chunks: int,
) -> tuple[set[str], int]:
    if max_chunks <= 0:
        raise ValueError("max_chunks 必须为正整数")

    work_ids: set[str] = set()
    count = 0
    for chunk in _read_jsonl(chunk_path):
        if count >= max_chunks:
            break
        work_id = chunk.get("work_id")
        if not isinstance(work_id, str) or not work_id:
            raise ValueError(f"Chunk row {count} 缺少有效 work_id")
        work_ids.add(work_id)
        count += 1
    return work_ids, count


def _insert_works(
    connection: sqlite3.Connection,
    work_path: Path,
    *,
    batch_size: int,
    allowed_work_ids: set[str] | None = None,
) -> int:
    rows: list[tuple[object, ...]] = []
    count = 0
    sql = (
        "INSERT INTO works "
        "(work_id, title, author, dynasty, source_record_id) "
        "VALUES (?, ?, ?, ?, ?)"
    )
    for work in _read_jsonl(work_path):
        work_id = work.get("work_id")
        if not isinstance(work_id, str) or not work_id:
            raise ValueError("Work JSONL 存在缺少 work_id 的记录")
        if allowed_work_ids is not None and work_id not in allowed_work_ids:
            continue
        rows.append(
            (
                work_id,
                work.get("title"),
                work.get("author"),
                work.get("dynasty"),
                work.get("source_record_id"),
            )
        )
        if len(rows) >= batch_size:
            connection.executemany(sql, rows)
            connection.commit()
            count += len(rows)
            rows.clear()
    if rows:
        connection.executemany(sql, rows)
        connection.commit()
        count += len(rows)
    return count


def _insert_chunks(
    connection: sqlite3.Connection,
    chunk_path: Path,
    *,
    batch_size: int,
    min_n: int,
    max_n: int,
    max_chunks: int | None = None,
) -> int:
    chunk_rows: list[tuple[object, ...]] = []
    fts_rows: list[tuple[int, str]] = []
    count = 0
    chunk_sql = (
        "INSERT INTO chunks "
        "(rowid, chunk_id, work_id, text, start, end) "
        "VALUES (?, ?, ?, ?, ?, ?)"
    )
    fts_sql = "INSERT INTO chunk_fts (rowid, grams) VALUES (?, ?)"

    for logical_row, chunk in enumerate(_read_jsonl(chunk_path)):
        if max_chunks is not None and logical_row >= max_chunks:
            break
        text = chunk.get("text")
        if not isinstance(text, str) or not text:
            raise ValueError(f"Chunk row {logical_row} 缺少有效 text")
        grams = character_ngrams(text, min_n=min_n, max_n=max_n)
        sqlite_rowid = logical_row + 1
        chunk_rows.append(
            (
                sqlite_rowid,
                chunk.get("chunk_id"),
                chunk.get("work_id"),
                text,
                chunk.get("start"),
                chunk.get("end"),
            )
        )
        fts_rows.append((sqlite_rowid, " ".join(grams)))

        if len(chunk_rows) >= batch_size:
            connection.executemany(chunk_sql, chunk_rows)
            connection.executemany(fts_sql, fts_rows)
            connection.commit()
            count += len(chunk_rows)
            chunk_rows.clear()
            fts_rows.clear()

    if chunk_rows:
        connection.executemany(chunk_sql, chunk_rows)
        connection.executemany(fts_sql, fts_rows)
        connection.commit()
        count += len(chunk_rows)
    return count


def build_bm25_index(
    *,
    work_path: Path,
    chunk_path: Path,
    output_dir: Path,
    chunk_policy: str,
    min_n: int = DEFAULT_MIN_N,
    max_n: int = DEFAULT_MAX_N,
    batch_size: int = DEFAULT_BATCH_SIZE,
    expected_chunks: int | None = None,
    max_chunks: int | None = None,
    force: bool = False,
) -> BM25Manifest:
    if chunk_policy not in CHUNK_PATHS:
        raise ValueError(f"未知 chunk policy：{chunk_policy!r}")
    if batch_size <= 0:
        raise ValueError("batch_size 必须为正整数")
    if max_chunks is not None and max_chunks <= 0:
        raise ValueError("max_chunks 必须为正整数")

    work_path = work_path.expanduser().resolve()
    chunk_path = chunk_path.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    if not work_path.is_file():
        raise ValueError(f"Work JSONL 不存在：{work_path}")
    if not chunk_path.is_file():
        raise ValueError(f"Chunk JSONL 不存在：{chunk_path}")

    work_sha256 = sha256_file(work_path)
    chunk_sha256 = sha256_file(chunk_path)

    output_dir.mkdir(parents=True, exist_ok=True)
    db_path = output_dir / "index.sqlite3"
    manifest_path = output_dir / "manifest.json"
    temp_db_path = output_dir / "index.sqlite3.tmp"

    if (db_path.exists() or manifest_path.exists()) and not force:
        raise ValueError(
            f"BM25 Artifact 已存在：{output_dir}；如需重建请传 --force"
        )
    for path in (db_path, manifest_path, temp_db_path):
        if force and path.exists():
            path.unlink()
    if temp_db_path.exists():
        temp_db_path.unlink()

    allowed_work_ids = None
    sampled_chunks = None
    if max_chunks is not None:
        allowed_work_ids, sampled_chunks = collect_chunk_work_ids(
            chunk_path,
            max_chunks=max_chunks,
        )

    build_started = time.perf_counter()
    connection = sqlite3.connect(temp_db_path)
    try:
        _check_fts5(connection)
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        connection.execute("PRAGMA temp_store = MEMORY")
        _create_schema(connection)

        work_count = _insert_works(
            connection,
            work_path,
            batch_size=batch_size,
            allowed_work_ids=allowed_work_ids,
        )
        chunk_count = _insert_chunks(
            connection,
            chunk_path,
            batch_size=batch_size,
            min_n=min_n,
            max_n=max_n,
            max_chunks=max_chunks,
        )
        if expected_chunks is not None and chunk_count != expected_chunks:
            raise ValueError(
                f"Chunk 实际 {chunk_count:,} 条，预期 {expected_chunks:,} 条"
            )

        connection.execute("INSERT INTO chunk_fts(chunk_fts) VALUES('optimize')")
        connection.execute("ANALYZE")
        connection.commit()
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        connection.close()

    temp_db_path.replace(db_path)
    build_elapsed = time.perf_counter() - build_started
    database_bytes = db_path.stat().st_size
    manifest: BM25Manifest = {
        "status": "complete",
        "engine": "sqlite_fts5",
        "ranking": "bm25",
        "term_representation": "character_ngram",
        "chunk_policy": chunk_policy,
        "min_n": min_n,
        "max_n": max_n,
        "works": work_count,
        "chunks": chunk_count,
        "max_chunks": max_chunks,
        "sampled_chunks_seen": sampled_chunks,
        "database_bytes": database_bytes,
        "database_mib": database_bytes / (1024 * 1024),
        "build_elapsed_seconds": build_elapsed,
        "chunks_per_second": chunk_count / build_elapsed if build_elapsed else None,
        "work_path": str(work_path),
        "work_sha256": work_sha256,
        "chunk_path": str(chunk_path),
        "chunk_sha256": chunk_sha256,
        "database": db_path.name,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    temp_manifest = manifest_path.with_suffix(".json.tmp")
    temp_manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temp_manifest.replace(manifest_path)
    return manifest


def load_manifest(index_dir: Path) -> BM25Manifest:
    manifest_path = index_dir / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError(f"BM25 manifest 不存在：{manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("BM25 manifest 必须是 JSON 对象")
    if manifest.get("status") != "complete":
        raise ValueError(
            f"BM25 Artifact 尚未完成：status={manifest.get('status')!r}"
        )
    if manifest.get("engine") != "sqlite_fts5":
        raise ValueError(f"未知 lexical engine：{manifest.get('engine')!r}")
    return _MANIFEST_ADAPTER.validate_python(manifest)


def search_bm25(
    *,
    query: str,
    index_dir: Path,
    top_k: int = DEFAULT_TOP_K,
    before_dynasty: str | None = None,
    probe_text: str | None = None,
    probe_author: str | None = None,
) -> BM25SearchResult:
    if top_k <= 0:
        raise ValueError("top_k 必须为正整数")
    if probe_author and not probe_text:
        raise ValueError("probe_author 必须和 probe_text 一起使用")

    index_dir = index_dir.expanduser().resolve()
    manifest = load_manifest(index_dir)
    db_path = index_dir / manifest["database"]
    if not db_path.is_file():
        raise ValueError(f"BM25 database 不存在：{db_path}")

    match_query = build_match_query(
        query,
        min_n=manifest["min_n"],
        max_n=manifest["max_n"],
    )
    chronology = None
    allowed_dynasties: list[str] | None = None
    if before_dynasty:
        allowed_dynasties = sorted(candidate_prior_dynasties(before_dynasty))
        chronology = {
            "before_dynasty": before_dynasty,
            "allowed_dynasties": allowed_dynasties,
        }

    sql = """
        SELECT
            c.rowid,
            c.chunk_id,
            c.work_id,
            c.text,
            c.start,
            c.end,
            w.title,
            w.author,
            w.dynasty,
            w.source_record_id,
            bm25(chunk_fts) AS raw_score
        FROM chunk_fts
        JOIN chunks AS c ON c.rowid = chunk_fts.rowid
        JOIN works AS w ON w.work_id = c.work_id
        WHERE chunk_fts MATCH ?
    """
    params: list[object] = [match_query]
    if allowed_dynasties is not None:
        if not allowed_dynasties:
            raise ValueError("朝代过滤后没有允许的 dynasty")
        placeholders = ", ".join("?" for _ in allowed_dynasties)
        sql += f" AND w.dynasty IN ({placeholders})"
        params.extend(allowed_dynasties)
    sql += " ORDER BY raw_score ASC, c.rowid ASC LIMIT ?"
    params.append(top_k)

    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(sql, params).fetchall()
    finally:
        connection.close()

    ranking: list[BM25RankedHit] = []
    probe_matches: list[BM25RankedHit] = []
    for rank, row in enumerate(rows, 1):
        result: BM25RankedHit = {
            "rank": rank,
            "bm25_score": -float(row["raw_score"]),
            "global_row": int(row["rowid"]) - 1,
            "chunk": {
                "chunk_id": row["chunk_id"],
                "text": row["text"],
                "start": row["start"],
                "end": row["end"],
            },
            "work": {
                "work_id": row["work_id"],
                "title": row["title"],
                "author": row["author"],
                "dynasty": row["dynasty"],
                "source_record_id": row["source_record_id"],
            },
        }
        ranking.append(result)
        if (
            probe_text
            and probe_text in row["text"]
            and (probe_author is None or probe_author == row["author"])
        ):
            probe_matches.append(result)

    return {
        "query": query,
        "engine": manifest["engine"],
        "ranking_method": manifest["ranking"],
        "term_representation": manifest["term_representation"],
        "chunk_policy": manifest["chunk_policy"],
        "ngram_range": [manifest["min_n"], manifest["max_n"]],
        "top_k": top_k,
        "chronology_filter": chronology,
        "ranking": ranking,
        "probes": probe_matches,
        "note": (
            "BM25 只负责字面候选召回；当前 probe 只报告 Top-K 内命中，"
            "不把 BM25 分数解释成文学关系强度。"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="character n-gram + SQLite FTS5 BM25 lexical retrieval"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser = subparsers.add_parser("build", help="建立 BM25 lexical index")
    build_parser.add_argument(
        "--chunk-policy",
        choices=sorted(CHUNK_PATHS),
        required=True,
    )
    build_parser.add_argument("--works", type=Path, default=DEFAULT_WORKS)
    build_parser.add_argument("--chunks", type=Path)
    build_parser.add_argument("--output-dir", type=Path)
    build_parser.add_argument("--min-n", type=int, default=DEFAULT_MIN_N)
    build_parser.add_argument("--max-n", type=int, default=DEFAULT_MAX_N)
    build_parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    build_parser.add_argument("--expected-chunks", type=int)
    build_parser.add_argument(
        "--max-chunks",
        type=int,
        help="只索引前 N 个 Chunk，用于真实规模预估",
    )
    build_parser.add_argument("--force", action="store_true")

    search_parser = subparsers.add_parser("search", help="查询 BM25 lexical index")
    search_parser.add_argument("query")
    search_parser.add_argument("--index-dir", type=Path, required=True)
    search_parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    search_parser.add_argument("--before-dynasty")
    search_parser.add_argument("--probe-text")
    search_parser.add_argument("--probe-author")

    args = parser.parse_args()
    try:
        if args.command == "build":
            chunk_path = args.chunks or CHUNK_PATHS[args.chunk_policy]
            output_dir = args.output_dir or default_output_dir(
                args.chunk_policy,
                min_n=args.min_n,
                max_n=args.max_n,
            )
            result = build_bm25_index(
                work_path=args.works,
                chunk_path=chunk_path,
                output_dir=output_dir,
                chunk_policy=args.chunk_policy,
                min_n=args.min_n,
                max_n=args.max_n,
                batch_size=args.batch_size,
                expected_chunks=(
                    args.expected_chunks
                    if args.expected_chunks is not None
                    else (
                        args.max_chunks
                        if args.max_chunks is not None
                        else EXPECTED_CHUNKS[args.chunk_policy]
                    )
                ),
                max_chunks=args.max_chunks,
                force=args.force,
            )
        else:
            result = search_bm25(
                query=args.query,
                index_dir=args.index_dir,
                top_k=args.top_k,
                before_dynasty=args.before_dynasty,
                probe_text=args.probe_text,
                probe_author=args.probe_author,
            )
    except (ValueError, RuntimeError, sqlite3.Error) as exc:
        raise SystemExit(str(exc)) from exc

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
