"""Poeticus 作品只读查询使用的 PostgreSQL 连接。

模块导入及应用启动时不建立数据库连接；每个请求建立短生命周期连接，
在当前规模下不需要连接池。"""
import logging
import os
from collections.abc import Callable, Iterator
from typing import cast

import psycopg
from dotenv import load_dotenv
from fastapi import HTTPException
from psycopg.rows import DictRow, dict_row

logger = logging.getLogger(__name__)


def get_connection() -> Iterator[psycopg.Connection[DictRow]]:
    """提供一个只读数据库连接；异常中不得暴露凭据。

    输入：进程环境或私人 .env 中的 POETICUS_DATABASE_URL。
    输出：SELECT 查询结果为字典行的 psycopg Connection。
    """
    load_dotenv()
    dsn = os.getenv("POETICUS_DATABASE_URL")
    if not dsn:
        raise HTTPException(status_code=503, detail="作品数据库尚未配置")
    try:
        # Psycopg 的 connect() 在运行时正确支持 dict_row，但 Pyright
        # 可能推断为 Connection[TupleRow]（psycopg/psycopg#1257）。
        # 只在这一处边界适配第三方函数的类型。
        connect_dict_rows = cast(
            Callable[..., psycopg.Connection[DictRow]],
            psycopg.connect,
        )
        with connect_dict_rows(dsn, row_factory=dict_row, connect_timeout=5) as conn:
            conn.execute("SET TRANSACTION READ ONLY")
            yield conn
    except psycopg.Error as exc:
        logger.warning("Corpus DB request failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=503, detail="作品数据库暂时不可用"
        ) from exc
