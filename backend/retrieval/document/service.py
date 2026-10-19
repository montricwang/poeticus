"""PostgreSQL + pgvector + BM25 文献检索。

在用户主动调用 search_documents 时才懒加载本地 Qwen Embedding，不改变 Web 服务启动负担。
Document 表是原文唯一数据源；不能以旧实验 JSON 充当线上检索库。
"""
from __future__ import annotations

import os
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Sequence

import psycopg
from dotenv import load_dotenv

from backend.data_paths import MODELS_ROOT
from backend.evidence.schema import EvidenceItem, EvidenceSource
from backend.retrieval.document.lexical import SectionBM25

logger = logging.getLogger(__name__)

MODEL_ID = "Qwen/Qwen3-Embedding-0.6B"
DEFAULT_MODEL_PATH = MODELS_ROOT / "Qwen3-Embedding-0.6B-7c0e29cfcdf2"
CANDIDATE_DEPTH = 50
RRF_K = 60
TOP_K = 5
MAX_QUERIES = 3
MAX_EVIDENCE_CHARS = 1600


class DocumentRetrievalError(RuntimeError):
    """Document Corpus 未就绪或查询失败（不含敏感数据库信息）。"""


@dataclass(frozen=True)
class DocumentSearchResult:
    queries: list[str]
    evidences: list[EvidenceItem]


@lru_cache(maxsize=1)
def _query_encoder(model_path: str) -> Any:
    # 不在 Agent import 或应用启动阶段导入 torch / sentence-transformers。
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(model_path, device="cpu", local_files_only=True)
    model.max_seq_length = 512
    return model


def _encode_query(text: str, model_path: Path) -> str:
    import numpy as np

    model = _query_encoder(str(model_path))
    vec = np.asarray(
        model.encode(
            [text], prompt_name="query", batch_size=1,
            normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False,
        ),
        dtype=np.float32,
    )
    if vec.shape != (1, 1024) or not np.isfinite(vec).all():
        raise DocumentRetrievalError("文献查询向量无效")
    return "[" + ",".join(format(float(x), ".9g") for x in vec[0]) + "]"


def _rrf(lexical: Sequence[tuple[str, float]], dense: Sequence[tuple[str, float]]) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    for channel in (lexical, dense):
        for idx, (key, _) in enumerate(channel):
            scores[key] = scores.get(key, 0.0) + 1 / (RRF_K + idx + 1)
    return sorted(scores.items(), key=lambda row: (-row[1], row[0]))[:TOP_K]


class DocumentRetrieval:
    """按本地显式 opt-in 注册；不依赖诗句 FAISS 服务，且不能误启用到 Railway。"""

    def __init__(self, *, model_path: Path = DEFAULT_MODEL_PATH, dsn: str | None = None) -> None:
        self.model_path = model_path
        self._dsn = dsn

    @property
    def enabled(self) -> bool:
        load_dotenv()
        return (
            os.getenv("POETICUS_DOCUMENT_RAG_ENABLED", "").strip().lower() in ("1", "true", "yes")
            and self.model_path.is_dir()
            and bool(self._dsn or os.getenv("POETICUS_DATABASE_URL"))
        )

    def search(self, question: str, *, extra_queries: Sequence[str] = ()) -> DocumentSearchResult:
        question = question.strip()
        if not question or len(question) > 1200:
            raise ValueError("文献检索问题不能为空且不能超过 1200 字")
        if len(extra_queries) > MAX_QUERIES - 1 or any(
            not isinstance(x, str) or not x.strip() or len(x) > 180 for x in extra_queries
        ):
            raise ValueError("最多提供两条各不超过 180 字的扩展查询")

        queries = list(dict.fromkeys([question, *(q.strip() for q in extra_queries)]))
        if not self.enabled:
            raise DocumentRetrievalError("本地 Document RAG 未启用或查询模型缺失")
        dsn = self._dsn or os.getenv("POETICUS_DATABASE_URL")
        if not dsn:
            raise DocumentRetrievalError("Document Corpus 数据库尚未配置")

        try:
            with psycopg.connect(dsn, connect_timeout=5) as conn:
                conn.execute("SET TRANSACTION READ ONLY")
                ambiguous = conn.execute(
                    """SELECT document_id FROM document_corpus.document_versions
                       GROUP BY document_id HAVING COUNT(*) > 1 LIMIT 1"""
                ).fetchone()
                if ambiguous:
                    raise DocumentRetrievalError(
                        "同一文献存在多个来源版本，尚未指定当前检索版本；拒绝混合原文"
                    )
                # 原文、标题、定位和版本信息全部从数据库取得。当前规模下 BM25 每次临时建立，
                # 新增书目不会因为进程内缓存而被遗漏。
                records = conn.execute(
                    """SELECT n.source_key, n.title, n.body_text,
                              n.source_locator, n.id::text AS node_id,
                              d.id::text AS document_id, d.title AS book_title, d.author,
                              v.id::text AS version_id, v.source_uri, v.edition_label,
                              v.rights_status,
                              parent.title AS parent_title, parent.node_type AS parent_type,
                              grandparent.title AS grandparent_title,
                              grandparent.node_type AS grandparent_type
                       FROM document_corpus.document_nodes n
                       JOIN document_corpus.document_versions v ON v.id=n.version_id
                       JOIN document_corpus.documents d ON d.id=v.document_id
                       LEFT JOIN document_corpus.document_nodes parent ON parent.id=n.parent_id
                       LEFT JOIN document_corpus.document_nodes grandparent ON grandparent.id=parent.parent_id
                       WHERE n.node_type='section'
                         AND EXISTS (
                           SELECT 1 FROM document_corpus.retrieval_chunks ck
                           JOIN document_corpus.chunk_embeddings em ON em.chunk_id=ck.id
                           WHERE ck.node_id=n.id AND em.model_id=%s
                         )
                       ORDER BY d.title, n.sort_order""", (MODEL_ID,)
                ).fetchall()
                if not records:
                    raise DocumentRetrievalError("数据库中没有可用的文献检索向量")
                index: dict[str, dict[str, Any]] = {}
                sections: list[dict[str, str]] = []
                for (key, title, body, locator, node_id, doc_id, book_title, author,
                     version_id, source_uri, edition, rights, parent_title, parent_type,
                     grandparent_title, grandparent_type) in records:
                    if not isinstance(locator, dict):
                        raise DocumentRetrievalError("原文定位数据无效")
                    section = {
                        "doc": book_title,
                        "file": locator["epub_file"],
                        "section_id": str(locator["section_id"]),
                        "title": title, "text": body,
                    }
                    if "|".join((section["doc"], section["file"], section["section_id"])) != key:
                        raise DocumentRetrievalError("文献来源定位与检索索引不一致")
                    sections.append(section)
                    index[key] = {
                        "title": title, "text": body, "locator": locator,
                        "node_id": node_id, "document_id": doc_id,
                        "book": book_title, "author": author,
                        "version_id": version_id, "source_uri": source_uri,
                        "edition": edition, "rights_status": rights,
                        "volume": parent_title if parent_type == "volume" else grandparent_title,
                        "group": parent_title if parent_type == "group" else None,
                    }

                bm25 = SectionBM25(sections)
                scores: dict[str, float] = {}
                for query in queries:
                    lexical = bm25.search(query, CANDIDATE_DEPTH)
                    vector = _encode_query(query, self.model_path)
                    dense = conn.execute(
                        """SELECT n.source_key, 1-(em.embedding <=> %s::vector) AS similarity
                           FROM document_corpus.chunk_embeddings em
                           JOIN document_corpus.retrieval_chunks ck ON ck.id=em.chunk_id
                           JOIN document_corpus.document_nodes n ON n.id=ck.node_id
                           WHERE em.model_id=%s
                           ORDER BY em.embedding <=> %s::vector, n.source_key
                           LIMIT %s""", (vector, MODEL_ID, vector, CANDIDATE_DEPTH)
                    ).fetchall()
                    ranked = _rrf(lexical, [(key, float(score)) for key, score in dense])
                    for rank, (key, _) in enumerate(ranked, 1):
                        scores[key] = scores.get(key, 0.0) + 1 / (RRF_K + rank)

        except (psycopg.Error, ImportError, OSError) as exc:
            logger.warning("Document RAG 查询失败：%s", type(exc).__name__)
            raise DocumentRetrievalError("本地文献检索服务暂时不可用") from exc

        ranked = sorted(scores, key=lambda key: (-scores[key], key))[:TOP_K]
        evidences: list[EvidenceItem] = []
        for key in ranked:
            r = index[key]
            evidences.append(EvidenceItem(
                anchor=r["title"],
                type="commentary",
                text=r["text"][:MAX_EVIDENCE_CHARS],
                provider="document_corpus",
                status="candidate",
                source=EvidenceSource(
                    title=r["title"], work=r["book"], author=r["author"],
                    url=r["source_uri"],
                ),
                metadata={
                    "document_id": r["document_id"], "node_id": r["node_id"],
                    "version_id": r["version_id"], "source_key": key,
                    "volume": r["volume"], "group": r["group"],
                    "edition_label": r["edition"],
                    "source_locator": r["locator"],
                    "rights_status": r["rights_status"],
                    "truncated": len(r["text"]) > MAX_EVIDENCE_CHARS,
                },
            ))
        return DocumentSearchResult(queries=queries, evidences=evidences)


document_retrieval = DocumentRetrieval()
