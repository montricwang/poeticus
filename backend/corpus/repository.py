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
        terms.append("cipai = %s")
        values.append(cipai)
    if q:
        # STRPOS checks literal substrings: % and _ are not LIKE wildcards.
        terms.append(
            "("
            "STRPOS(LOWER(COALESCE(author, '')), LOWER(%s)) > 0 OR "
            "STRPOS(LOWER(COALESCE(cipai, '')), LOWER(%s)) > 0 OR "
            "STRPOS(LOWER(COALESCE(title, '')), LOWER(%s)) > 0 OR "
            "STRPOS(LOWER(body_segments::text), LOWER(%s)) > 0"
            ")"
        )
        values.extend([q] * 4)
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
