"""Plain read-only SQL for the reader corpus, independent of FastAPI.

Only query poems. Do NOT expose poem_source_texts, source offsets, private
annotations/commentaries or source-only material to an HTTP response.
"""
from uuid import UUID

from psycopg import Connection


def _filters(author: str | None, cipai: str | None, q: str | None):
    terms: list[str] = []
    values: list[str] = []
    if author:
        terms.append("author = %s")
        values.append(author)
    if cipai:
        # One visible '词牌' field accepts either the original tune or an
        # author-coined yusheng title, without conflating the stored columns.
        terms.append("(cipai = %s OR yusheng_title = %s)")
        values.extend([cipai, cipai])
    if q:
        # 空白分隔的多词：词与词 AND、同一个词跨列 OR；每词仍是字面子串。
        # STRPOS 不将 % 和 _ 当成 LIKE 通配符；不进行自动中文分词。
        for word in q.split():
            terms.append(
                "("
                "STRPOS(LOWER(COALESCE(author, '')), LOWER(%s)) > 0 OR "
                "STRPOS(LOWER(COALESCE(cipai, '')), LOWER(%s)) > 0 OR "
                "STRPOS(LOWER(COALESCE(yusheng_title, '')), LOWER(%s)) > 0 OR "
                "STRPOS(LOWER(COALESCE(title, '')), LOWER(%s)) > 0 OR "
                "STRPOS(LOWER(body_segments::text), LOWER(%s)) > 0"
                ")"
            )
            values.extend([word] * 5)
    return (" WHERE " + " AND ".join(terms)) if terms else "", values


def list_poems(
    conn: Connection,
    *,
    author: str | None,
    cipai: str | None,
    q: str | None,
    limit: int,
    offset: int,
) -> tuple[list[dict], int]:
    """Input: optional filters and page; output: (metadata-only rows, total)."""
    where_sql, params = _filters(author, cipai, q)
    total = conn.execute(
        "SELECT COUNT(*) AS total FROM poems" + where_sql, tuple(params)
    ).fetchone()["total"]
    rows = conn.execute(
        """SELECT id, source_order, collection, author, cipai, title, yusheng_title,
                  COALESCE(LEFT(body_segments->>0, 60), '') AS incipit,
                  review_status
           FROM poems"""
        + where_sql
        + " ORDER BY source_order LIMIT %s OFFSET %s",
        (*params, limit, offset),
    ).fetchall()
    return rows, total


def get_poem(conn: Connection, poem_id: UUID) -> dict | None:
    """Input: permanent UUID; output: one reader record or None."""
    return conn.execute(
        """SELECT id, source_order, collection, author, cipai, title, yusheng_title,
                  body_segments, prefaces, review_status, text_version
           FROM poems WHERE id = %s""",
        (poem_id,),
    ).fetchone()
