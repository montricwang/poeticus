"""Private SQL operations: caller supplies an internal UUID from verified Clerk auth.

Every user-owned operation carries the internal user_id in SQL predicates;
a client-generated conversation UUID is a locator, never an authorization token.
"""

import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID, uuid4

import psycopg
from fastapi import HTTPException
from psycopg.rows import dict_row

logger = logging.getLogger(__name__)


@contextmanager
def _db() -> Iterator[psycopg.Connection]:
    dsn = os.getenv("POETICUS_DATABASE_URL", "").strip()
    if not dsn:
        raise HTTPException(status_code=503, detail="私人数据库尚未配置")
    try:
        with psycopg.connect(dsn, connect_timeout=5, row_factory=dict_row) as conn:
            yield conn
    except psycopg.Error as exc:
        logger.warning("Private database failure: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="私人数据库暂时不可用") from exc


def _check_owner(conn: psycopg.Connection, user_id: UUID, conversation_id: UUID) -> dict:
    row = conn.execute(
        "SELECT id, poem_id FROM app_conversations WHERE id=%s AND user_id=%s",
        (conversation_id, user_id),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="对话不存在")
    return row


def get_memory_opt_in(user_id: UUID) -> bool:
    with _db() as conn:
        row = conn.execute("SELECT memory_opt_in FROM app_users WHERE id=%s", (user_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="账户不存在")
    return row["memory_opt_in"] is True


def set_memory_opt_in(user_id: UUID, enabled: bool) -> bool:
    with _db() as conn:
        row = conn.execute(
            "UPDATE app_users SET memory_opt_in=%s WHERE id=%s RETURNING memory_opt_in",
            (enabled, user_id),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="账户不存在")
    return row["memory_opt_in"] is True


def begin_turn(
    user_id: UUID,
    conversation_id: UUID,
    poem_id: str,
    turn_number: int,
    question: str,
) -> UUID:
    """Create a conversation once, or require ownership; persist source before inference."""
    with _db() as conn:
        conn.execute(
            """INSERT INTO app_conversations (id, user_id, poem_id)
               VALUES (%s, %s, %s) ON CONFLICT (id) DO NOTHING""",
            (conversation_id, user_id, poem_id),
        )
        own = _check_owner(conn, user_id, conversation_id)
        if own["poem_id"] != poem_id:
            raise HTTPException(status_code=409, detail="对话归属作品不一致")

        # A retried identical question is idempotent. Editing an old question
        # requires an explicit conversation revision workflow, not silent overwrite.
        previous = conn.execute(
            """SELECT id, content FROM app_messages
               WHERE conversation_id=%s AND turn_number=%s AND role='user'""",
            (conversation_id, turn_number),
        ).fetchone()
        if previous:
            if previous["content"] != question:
                raise HTTPException(status_code=409, detail="历史提问已存在，请新建讨论")
            return previous["id"]
        message_id = uuid4()
        conn.execute(
            """INSERT INTO app_messages (id, conversation_id, turn_number, role, content)
               VALUES (%s, %s, %s, 'user', %s)""",
            (message_id, conversation_id, turn_number, question),
        )
        conn.execute(
            "UPDATE app_conversations SET updated_at=now() WHERE id=%s AND user_id=%s",
            (conversation_id, user_id),
        )
        return message_id


def finish_turn(user_id: UUID, conversation_id: UUID, turn_number: int, answer: str) -> None:
    """Persist a completed assistant reply before reporting SSE done."""
    with _db() as conn:
        _check_owner(conn, user_id, conversation_id)
        conn.execute(
            """INSERT INTO app_messages (id, conversation_id, turn_number, role, content)
               VALUES (%s, %s, %s, 'assistant', %s)
               ON CONFLICT (conversation_id, turn_number, role)
               DO UPDATE SET content=EXCLUDED.content""",
            (uuid4(), conversation_id, turn_number, answer),
        )
        conn.execute(
            "UPDATE app_conversations SET updated_at=now() WHERE id=%s AND user_id=%s",
            (conversation_id, user_id),
        )


def list_conversations(user_id: UUID, limit: int = 30) -> list[dict]:
    with _db() as conn:
        return conn.execute(
            """SELECT id, poem_id, created_at, updated_at
               FROM app_conversations WHERE user_id=%s
               ORDER BY updated_at DESC, id DESC LIMIT %s""",
            (user_id, limit),
        ).fetchall()


def read_conversation(user_id: UUID, conversation_id: UUID) -> dict:
    with _db() as conn:
        own = _check_owner(conn, user_id, conversation_id)
        messages = conn.execute(
            """SELECT id, turn_number, role, content, created_at
               FROM app_messages WHERE conversation_id=%s
               ORDER BY turn_number, CASE role WHEN 'user' THEN 0 ELSE 1 END""",
            (conversation_id,),
        ).fetchall()
    return {**own, "messages": messages}


def ensure_owns_conversation(user_id: UUID, conversation_id: UUID) -> None:
    """Authorize the locator before touching memory or other external services."""
    with _db() as conn:
        _check_owner(conn, user_id, conversation_id)


def delete_conversation(user_id: UUID, conversation_id: UUID) -> None:
    with _db() as conn:
        _check_owner(conn, user_id, conversation_id)
        conn.execute(
            "DELETE FROM app_conversations WHERE id=%s AND user_id=%s",
            (conversation_id, user_id),
        )
