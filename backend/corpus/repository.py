"""阅读作品库的只读 SQL，与 FastAPI 解耦。

Only query poems. Do NOT expose poem_source_texts, source offsets, private
annotations/commentaries or source-only material to an HTTP response.
"""
from uuid import UUID

from psycopg import Connection
from psycopg.rows import DictRow


def _filters(author: str | None, cipai: str | None, q: str | None):
    terms: list[str] = []
    values: list[str] = []
    if author:
        terms.append("author = %s")
        values.append(author)
    if cipai:
        # 前端只有一个可见“词牌”筛选框，因此查询时同时匹配原词牌与寓声名；
        # 数据库存储仍保持两列独立。
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
    conn: Connection[DictRow],
    *,
    author: str | None,
    cipai: str | None,
    q: str | None,
    limit: int,
    offset: int,
) -> tuple[list[DictRow], int]:
    """输入可选筛选和分页参数，返回题录行与总数。"""
    where_sql, params = _filters(author, cipai, q)
    count_row = conn.execute(
        "SELECT COUNT(*) AS total FROM poems" + where_sql, tuple(params)
    ).fetchone()
    if count_row is None:
        raise RuntimeError("COUNT 查询未返回结果")
    total = int(count_row["total"])
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


def get_poem(conn: Connection[DictRow], poem_id: UUID) -> DictRow | None:
    """输入作品永久 UUID，返回一条阅读记录；不存在时返回 None。"""
    return conn.execute(
        """SELECT id, source_order, collection, author, cipai, title, yusheng_title,
                  body_segments, prefaces, review_status, text_version
           FROM poems WHERE id = %s""",
        (poem_id,),
    ).fetchone()
