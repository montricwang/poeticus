"""Opt-in, synthetic smoke-test corpus for a disposable cloud database.

No private EPUB, source evidence, or real-world literary claim is imported.
Run only with --apply and POETICUS_ENABLE_DEMO_SEED=true.
"""
from __future__ import annotations

import argparse
import os
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from scripts.corpus.db_import import migrate

# UUIDs are fixed so repeated deployments never duplicate demo entries.
DEMO_POEMS = (
    ("00000000-0000-4000-8000-000000000101", 1, "春日小景（测试）", "山前新雨过。", "柳外晚风来。"),
    ("00000000-0000-4000-8000-000000000102", 2, "秋窗即事（测试）", "窗前梧叶落。", "灯下读书声。"),
    ("00000000-0000-4000-8000-000000000103", 3, "夜泊随想（测试）", "远岸微灯照。", "平湖一棹轻。"),
)


def apply_demo_data(dsn: str) -> int:
    """Create schema via the real migration chain and insert a few safe examples."""
    with psycopg.connect(dsn, autocommit=True) as conn:
        migrate(conn)
        with conn.transaction():
            count = 0
            for poem_id, order, title, first_line, second_line in DEMO_POEMS:
                result = conn.execute(
                    """INSERT INTO poems (
                        id, source_record_id, source_order, collection, author,
                        cipai, title, yusheng_title, body_segments, prefaces,
                        inline_notes, lacunae, review_status, text_version
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO NOTHING""",
                    (
                        UUID(poem_id), f"demo-synthetic-{order}", order,
                        "Poeticus 合成测试作品", "测试作者", None, title, None,
                        Jsonb([first_line, second_line]), Jsonb([]),
                        Jsonb([]), Jsonb([]), "demo_synthetic", 1,
                    ),
                )
                count += result.rowcount
            return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize private cloud smoke-test corpus")
    parser.add_argument("--apply", action="store_true", help="Perform DB mutations")
    args = parser.parse_args()
    if not args.apply or os.getenv("POETICUS_ENABLE_DEMO_SEED") != "true":
        raise SystemExit("Seed disabled: requires --apply and POETICUS_ENABLE_DEMO_SEED=true")
    dsn = os.getenv("POETICUS_DATABASE_URL")
    if not dsn:
        raise SystemExit("POETICUS_DATABASE_URL is not configured")
    count = apply_demo_data(dsn)
    print(f"Synthetic test records inserted: {count}")


if __name__ == "__main__":
    main()
