"""Map verified Clerk subjects to stable internal Poeticus user UUIDs."""

import logging
import os
from uuid import UUID, uuid4

import psycopg
from fastapi import HTTPException

logger = logging.getLogger(__name__)


def _get_or_create_user(conn: psycopg.Connection, clerk_user_id: str) -> UUID:
    """Reuse one stable local UUID; concurrent first logins must not duplicate it."""
    row = conn.execute(
        """
        INSERT INTO app_users (id, clerk_user_id)
        VALUES (%s, %s)
        ON CONFLICT (clerk_user_id) DO NOTHING
        RETURNING id
        """,
        (uuid4(), clerk_user_id),
    ).fetchone()
    if row is None:
        row = conn.execute(
            "SELECT id FROM app_users WHERE clerk_user_id = %s",
            (clerk_user_id,),
        ).fetchone()
    if row is None:
        raise RuntimeError("Unable to resolve user after unique conflict")
    return row[0]


def get_or_create_user(clerk_user_id: str) -> UUID:
    """Create a minimal local account using only a server-verified Clerk ID."""
    if not clerk_user_id.startswith("user_"):
        raise ValueError("Expected a verified Clerk user subject")

    dsn = os.getenv("POETICUS_DATABASE_URL", "").strip()
    if not dsn:
        raise HTTPException(status_code=503, detail="用户数据库尚未配置")
    try:
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            return _get_or_create_user(conn, clerk_user_id)
    except (psycopg.Error, RuntimeError) as exc:
        # Never leak database credentials, account identifiers, or SQL in responses.
        logger.warning("User database request failed: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="用户数据库暂时不可用") from exc
