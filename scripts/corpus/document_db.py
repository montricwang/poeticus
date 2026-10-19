"""本地 Document Corpus：从原始 EPUB 核对四书，再幂等导入 PostgreSQL。

迁移分离：--migrate 只建文献表；--migrate-vectors 需本机 PostgreSQL 已支持 pgvector。
所有写操作只作用于 document_corpus schema，不改 poetry 的 public 表或现有 Agent。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import uuid
from collections import Counter
from pathlib import Path
from typing import Any, LiteralString, cast
from zipfile import ZipFile

import psycopg
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from ebooklib import epub
from psycopg import sql
from psycopg.types.json import Jsonb

from backend.data_paths import DATA_ROOT
from scripts.experiments.document_rag_dense_hybrid import (
    BATCH_SIZE, DEFAULT_CACHE, MODEL_ID, section_text,
)
from scripts.experiments.document_rag_lexical_baseline import (
    DEFAULT_CORPUS, checked_sections, section_key,
)

RAW_ROOT = DATA_ROOT / "document-corpus/raw"
MIGRATIONS_ROOT = Path(__file__).resolve().parents[2] / "db/document_migrations"
# 本轮来源清单是书目数据，不参与文献结构解析。后续新书只需追加登记。
BOOKS = {
    "人間詞話": ("王國維", "清末民初"),
    "樂府指迷": ("沈義父", "宋"),
    "白雨齋詞話": ("陳廷焯", "清"),
    "碧雞漫志": ("王灼", "宋"),
}
NAMESPACE = uuid.UUID("c54dd540-4be2-499d-beb1-aabbc8f74ac9")


def digest(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def uid(value: str) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, value)


def read_epub_sections(path: Path, expected: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """在真正的 XHTML Section 中重新提取标题/正文；拒绝旧 JSON 与 EPUB 漂移。

    原 EPUB 具有 data-mw-section-id 与 heading id；不据猜测生成不存在的锚点。
    """
    result: list[dict[str, Any]] = []
    with ZipFile(path) as archive:
        names = {name.rsplit("/", 1)[-1]: name for name in archive.namelist() if name.endswith(".xhtml")}
        html: dict[str, BeautifulSoup] = {}
        for original in expected:
            filename = original["file"]
            if filename not in names:
                raise ValueError(f"{path.name}: 缺失 XHTML 文件 {filename}")
            if filename not in html:
                html[filename] = BeautifulSoup(archive.read(names[filename]), "xml")
            match = html[filename].find_all("section", attrs={"data-mw-section-id":original["section_id"]})
            if len(match) != 1:
                raise ValueError(f"{path.name}: {filename} section_id={original['section_id']} 不唯一或不存在")
            section = match[0]
            heading = section.find(["h1", "h2", "h3", "h4", "h5", "h6"])
            if heading is None:
                raise ValueError(f"{filename}: 原文条目缺少标题")
            actual_title = heading.get_text(" ", strip=True)
            actual_heading_id = heading.get("id")
            heading.decompose()
            actual_text = section.get_text(" ", strip=True)
            if (actual_title, actual_heading_id, actual_text) != (
                original["title"], original["heading_id"], original["text"]
            ):
                raise ValueError(f"{path.name}: {filename}|{original['section_id']} 与旧语料不一致；拒绝静默覆盖")
            result.append({**original, "title": actual_title, "text": actual_text})
    return result


def prepare(corpus: Path = DEFAULT_CORPUS, raw_root: Path = RAW_ROOT) -> list[dict[str, Any]]:
    """返回带 EPUB 原文件哈希/来源 URI 的已核对数据；不连接数据库。"""
    sections = checked_sections(corpus)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for section in sections:
        grouped.setdefault(section["doc"], []).append(section)
    if set(grouped) != set(BOOKS):
        raise ValueError(f"输入语料书目与首批 EPUB 书目不符：{sorted(grouped)}")
    prepared = []
    for name, expected in grouped.items():
        raw = raw_root / f"{name}.epub"
        if not raw.is_file():
            raise FileNotFoundError(raw)
        book = epub.read_epub(str(raw))
        title = book.get_metadata("DC", "title")
        source = book.get_metadata("DC", "source")
        if not title or title[0][0] != name or not source:
            raise ValueError(f"{raw.name}: EPUB 书名或来源 URI 未确认")
        actual = read_epub_sections(raw, expected)
        source_uri = source[0][0]
        if not source_uri.startswith("https://zh.wikisource.org/"):
            raise ValueError(f"{raw.name}: 意外的原始来源 URI")
        prepared.append({
            "title": name, "author": BOOKS[name][0], "dynasty": BOOKS[name][1],
            "source_uri": source_uri,
            "source_file": raw.name, "source_sha256": digest(raw.read_bytes()),
            "source_rights_notice": [x[0] for x in book.get_metadata("DC", "rights")],
            "sections": actual,
        })
    return prepared


def node_rows(book: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """书→卷→可选组→节；每条现有 Section 暂派生一个等长 Chunk。"""
    doc_id = uid("document:" + book["title"])
    version_id = uid(f"version:{doc_id}:{book['source_sha256']}")
    rows: list[dict[str, Any]] = []
    chunks: list[dict[str, Any]] = []
    parents: dict[tuple[str, ...], uuid.UUID] = {}

    def add_node(key: str, node_type: str, parent: uuid.UUID | None, title: str, body: str, locator: dict[str, Any], metadata: dict[str, Any]) -> uuid.UUID:
        id_ = uid(f"node:{version_id}:{key}")
        rows.append({
            "id": id_, "version_id": version_id, "parent_id": parent, "node_type": node_type,
            "source_key": key, "sort_order": len(rows), "title": title,
            "body_text": body, "content_sha256": digest(body),
            "source_locator": locator, "metadata": metadata,
        })
        return id_

    for section in book["sections"]:
        vol = section["volume"]
        vol_key = ("volume", vol)
        if vol_key not in parents:
            parents[vol_key] = add_node(f"volume:{vol}", "volume", None, vol, "", {}, {})
        parent = parents[vol_key]
        group = section.get("group")
        if group and group != vol:
            group_key = ("group", vol, group)
            if group_key not in parents:
                parents[group_key] = add_node(f"group:{vol}/{group}", "group", parent, group, "", {}, {})
            parent = parents[group_key]
        locator = {
            "format": "wikisource_epub",
            "epub_file": section["file"],
            "section_id": section["section_id"],
            "heading_id": section["heading_id"],
        }
        section_id = add_node(
            section_key(section), "section", parent, section["title"],
            section["text"], locator, {},
        )
        text = section_text(section)
        chunks.append({
            "id": uid(f"chunk:{section_id}:0"), "node_id": section_id,
            "chunk_index": 0, "start_offset": 0, "end_offset": len(text),
            "text": text, "text_sha256": digest(text),
        })
    return rows, chunks


def migrate(conn: psycopg.Connection[Any], *, vectors: bool = False) -> None:
    sql_path = MIGRATIONS_ROOT / ("0002_pgvector.sql" if vectors else "0001_documents.sql")
    version = sql_path.stem
    if vectors:
        with conn.transaction():
            exists = conn.execute(
                "SELECT 1 FROM pg_available_extensions WHERE name = 'vector'"
            ).fetchone()
            if not exists:
                raise RuntimeError(
                    "当前本地 PostgreSQL 没有 pgvector；未改动数据库。"
                    "请先为 PostgreSQL 服务安装 pgvector，再执行 --migrate-vectors"
                )
    with conn.transaction():
        if vectors:
            relation = conn.execute("SELECT to_regclass('document_corpus.migrations')").fetchone()
            present = relation[0] if relation else None
            if present is None:
                raise RuntimeError("请先执行 --migrate")
            recorded = conn.execute(
                "SELECT 1 FROM document_corpus.migrations WHERE version=%s", (version,)
            ).fetchone()
            if recorded:
                print(f"Skip migration {version}")
                return
        else:
            relation = conn.execute("SELECT to_regclass('document_corpus.migrations')").fetchone()
            present = relation[0] if relation else None
            if present:
                recorded = conn.execute(
                    "SELECT 1 FROM document_corpus.migrations WHERE version=%s", (version,)
                ).fetchone()
                if recorded:
                    print(f"Skip migration {version}")
                    return
        # 只读取当前 Git 仓库内固定的迁移文件，不拼接外部输入。
        migration_sql = cast(LiteralString, sql_path.read_text(encoding="utf-8"))
        conn.execute(sql.SQL(migration_sql))
        conn.execute("INSERT INTO document_corpus.migrations(version) VALUES (%s)", (version,))
        print(f"Applied migration {version}")


def import_book(conn: psycopg.Connection[Any], book: dict[str, Any]) -> tuple[int, int]:
    doc_id = uid("document:" + book["title"])
    version_id = uid(f"version:{doc_id}:{book['source_sha256']}")
    author, dynasty = book["author"], book["dynasty"]
    conn.execute(
        """INSERT INTO document_corpus.documents(id,title,author,dynasty)
           VALUES (%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING""",
        (doc_id, book["title"], author, dynasty),
    )
    existing = conn.execute(
        "SELECT title,author,dynasty FROM document_corpus.documents WHERE id=%s", (doc_id,)
    ).fetchone()
    if existing != (book["title"], author, dynasty):
        raise ValueError(f"{book['title']}: 已存在不同的文献元数据")
    conn.execute(
        """INSERT INTO document_corpus.document_versions(
             id,document_id,edition_label,source_uri,source_file,source_sha256,rights_status,metadata
           ) VALUES (%s,%s,%s,%s,%s,%s,'unreviewed',%s)
           ON CONFLICT (id) DO NOTHING""",
        (version_id, doc_id, "Wikisource EPUB export (unverified text)",
         book["source_uri"], book["source_file"], book["source_sha256"],
         Jsonb({"epub_rights_notice": book["source_rights_notice"]})),
    )
    version = conn.execute(
        "SELECT document_id,source_file,source_uri,source_sha256 FROM document_corpus.document_versions WHERE id=%s",
        (version_id,),
    ).fetchone()
    if version != (doc_id, book["source_file"], book["source_uri"], book["source_sha256"]):
        raise ValueError(f"{book['title']}: 版本来源与已有数据库记录冲突")

    nodes, chunks = node_rows(book)
    # Node sort_order is global per version, and parent nodes always precede children.
    for n in nodes:
        conn.execute(
            """INSERT INTO document_corpus.document_nodes(
                 id, version_id, parent_id, node_type, source_key, sort_order, title, body_text,
                 content_sha256, source_locator, metadata
               ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (id) DO NOTHING""",
            (n["id"], n["version_id"], n["parent_id"], n["node_type"], n["source_key"],
             n["sort_order"], n["title"], n["body_text"], n["content_sha256"],
             Jsonb(n["source_locator"]), Jsonb(n["metadata"])),
        )
        old = conn.execute(
            """SELECT version_id,parent_id,node_type,source_key,sort_order,title,body_text,content_sha256,
                      source_locator,metadata
               FROM document_corpus.document_nodes WHERE id=%s""", (n["id"],)
        ).fetchone()
        expected = tuple(n[k] for k in (
            "version_id", "parent_id", "node_type", "source_key", "sort_order",
            "title", "body_text", "content_sha256", "source_locator", "metadata",
        ))
        if old != expected:
            raise ValueError(f"{book['title']}: 已有节点不一致：{n['source_key']}")
    for c in chunks:
        conn.execute(
            """INSERT INTO document_corpus.retrieval_chunks(
                 id,node_id,chunk_index,start_offset,end_offset,text,text_sha256
               ) VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING""",
            (c["id"], c["node_id"], c["chunk_index"], c["start_offset"],
             c["end_offset"], c["text"], c["text_sha256"]),
        )
        old = conn.execute(
            """SELECT node_id,chunk_index,start_offset,end_offset,text,text_sha256
               FROM document_corpus.retrieval_chunks WHERE id=%s""", (c["id"],)
        ).fetchone()
        expected = tuple(c[k] for k in (
            "node_id", "chunk_index", "start_offset", "end_offset", "text", "text_sha256",
        ))
        if old != expected:
            raise ValueError(f"{book['title']}: Chunk 内容漂移，拒绝覆盖")
    actual_nodes = conn.execute(
        "SELECT COUNT(*) FROM document_corpus.document_nodes WHERE version_id=%s", (version_id,)
    ).fetchone()
    actual_chunks = conn.execute(
        """SELECT COUNT(*) FROM document_corpus.retrieval_chunks c
           JOIN document_corpus.document_nodes n ON n.id=c.node_id
           WHERE n.version_id=%s""", (version_id,)
    ).fetchone()
    if actual_nodes is None or actual_nodes[0] != len(nodes) or actual_chunks is None or actual_chunks[0] != len(chunks):
        raise ValueError(f"{book['title']}: 数据库节点或 Chunk 数量与导入来源不一致")
    return len(nodes), len(chunks)


def import_all(conn: psycopg.Connection[Any], corpus: list[dict[str, Any]]) -> None:
    relation = conn.execute("SELECT to_regclass('document_corpus.document_nodes')").fetchone()
    if relation is None or relation[0] is None:
        raise RuntimeError("请先运行 --migrate")
    with conn.transaction():
        for book in corpus:
            n, k = import_book(conn, book)
            print(f"Verified/imported {book['title']}: {n} nodes / {k} chunks")


def import_vectors(conn: psycopg.Connection[Any], corpus: list[dict[str, Any]], cache: Path, corpus_path: Path) -> None:
    """导入实验时已有的缓存，不重新运行 Embedding；且只接受完全同版同序的向量。"""
    import numpy as np
    relation = conn.execute("SELECT to_regclass('document_corpus.chunk_embeddings')").fetchone()
    if relation is None or relation[0] is None:
        raise RuntimeError("pgvector 尚未建表，请先执行 --migrate-vectors")
    spec = json.loads((cache / "spec.json").read_text(encoding="utf-8"))
    rows = checked_sections(corpus_path)
    if (
        spec["corpus_sha256"] != digest(corpus_path.read_bytes())
        or spec["model_id"] != MODEL_ID
        or spec["dimension"] != 1024
        or spec["sections"] != len(rows)
        or spec["batch_size"] != BATCH_SIZE
    ):
        raise ValueError("Qwen 向量缓存与现有语料/模型/维度不一致")
    all_keys = [section_key(s) for b in corpus for s in b["sections"]]
    if [section_key(s) for s in rows] != all_keys:
        raise ValueError("当前 Document Source 排序已改变，无法安全复用向量")
    expected_batches = (len(rows) + BATCH_SIZE - 1) // BATCH_SIZE
    arrays = []
    for idx in range(expected_batches):
        matrix = np.load(cache / f"batch_{idx:04d}.npy", allow_pickle=False)
        nrows = min(BATCH_SIZE, len(rows) - idx * BATCH_SIZE)
        if matrix.shape != (nrows, 1024) or not np.isfinite(matrix).all():
            raise ValueError(f"向量缓存分片损坏: {idx}")
        arrays.append(matrix)
    all_vectors = np.concatenate(arrays)
    with conn.transaction():
        for section, vector, book in zip(rows, all_vectors, (b for b in corpus for _ in b["sections"]), strict=True):
            version_id = uid(f"version:{uid('document:' + book['title'])}:{book['source_sha256']}")
            node_id = uid(f"node:{version_id}:{section_key(section)}")
            chunk_id = uid(f"chunk:{node_id}:0")
            checksum = digest(section_text(section))
            v = "[" + ",".join(format(float(number), ".9g") for number in vector) + "]"
            conn.execute(
                """INSERT INTO document_corpus.chunk_embeddings(chunk_id,model_id,embedding,text_sha256)
                   VALUES (%s,%s,%s::vector,%s) ON CONFLICT (chunk_id,model_id) DO NOTHING""",
                (chunk_id, MODEL_ID, v, checksum),
            )
            old = conn.execute(
                """SELECT text_sha256 FROM document_corpus.chunk_embeddings
                   WHERE chunk_id=%s AND model_id=%s""", (chunk_id, MODEL_ID)
            ).fetchone()
            if old is None or old[0] != checksum:
                raise ValueError(f"向量模型或正文版本漂移：{section_key(section)}")
    print(f"Verified/imported {len(rows)} cached vectors ({MODEL_ID})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--check", action="store_true", help="只核对 EPUB 与原始 JSON，不连接数据库")
    action.add_argument("--migrate", action="store_true", help="建立四张 Document Corpus 表")
    action.add_argument("--import", dest="do_import", action="store_true", help="幂等导入四本 EPUB")
    action.add_argument("--migrate-vectors", action="store_true", help="pgvector 可用时建向量表")
    action.add_argument("--import-vectors", action="store_true", help="复用已缓存 Qwen Embedding")
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--raw", type=Path, default=RAW_ROOT)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    args = parser.parse_args()

    corpus: list[dict[str, Any]] = []
    if args.check or args.do_import or args.import_vectors:
        corpus = prepare(args.corpus, args.raw)
        print("Verified EPUB sections:", {b["title"]: len(b["sections"]) for b in corpus})
        if args.check:
            return
    load_dotenv()
    dsn = os.getenv("POETICUS_DATABASE_URL")
    if not dsn:
        raise RuntimeError("POETICUS_DATABASE_URL 未配置；拒绝执行数据库操作")
    with psycopg.connect(dsn, connect_timeout=5) as conn:
        # psycopg implicit transaction must be closed before calling conn.transaction().
        conn.autocommit = True
        if args.migrate:
            migrate(conn)
        elif args.migrate_vectors:
            migrate(conn, vectors=True)
        elif args.do_import:
            import_all(conn, corpus)
        elif args.import_vectors:
            import_vectors(conn, corpus, args.cache, args.corpus)


if __name__ == "__main__":
    main()
