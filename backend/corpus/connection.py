"""Poeticus 作品只读查询使用的 PostgreSQL 连接。

No database connection is created during module import or application startup.
Each request gets a short-lived connection; at this scale a pool is unnecessary.
"""
import logging
import os
from collections.abc import Iterator

import psycopg
from dotenv import load_dotenv
from fastapi import HTTPException
from psycopg.rows import dict_row

logger = logging.getLogger(__name__)


def get_connection() -> Iterator[psycopg.Connection]:
    """提供一个只读数据库连接；异常中不得暴露凭据。

    Input: POETICUS_DATABASE_URL in process env or private .env.
    Output: a psycopg Connection yielding dictionaries for SELECT results.
    """
    load_dotenv()
    dsn = os.getenv("POETICUS_DATABASE_URL")
    if not dsn:
        raise HTTPException(status_code=503, detail="作品数据库尚未配置")
    try:
        with psycopg.connect(dsn, row_factory=dict_row, connect_timeout=5) as conn:
            conn.execute("SET TRANSACTION READ ONLY")
            yield conn
    except psycopg.Error as exc:
        logger.warning("Corpus DB request failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=503, detail="作品数据库暂时不可用"
        ) from exc
