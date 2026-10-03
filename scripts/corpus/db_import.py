"""Local-only PostgreSQL migration and corpus import.

python -m scripts.corpus.db_import --check     # no database needed
python -m scripts.corpus.db_import --migrate   # PostgreSQL required
python -m scripts.corpus.db_import --import    # PostgreSQL required
"""
from __future__ import annotations

import argparse
import json
import os
import uuid
from collections import Counter
from pathlib import Path

from .adapter import ConvertedPoem, convert_corpus

DEFAULT_INPUT = Path("data/output/all_normalized.json")
MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "db/migrations"
LATEST_VERSION = "0003_yusheng_title"


def read_corpus(path: Path) -> list[ConvertedPoem]:
    with path.open(encoding="utf-8") as stream:
        return convert_corpus(json.load(stream))


def migrate(conn) -> None:
    """Apply pending numbered SQL migrations; keep prior versions immutable."""
    migration_files = sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9][0-9]_*.sql"))
    if not migration_files or migration_files[-1].stem != LATEST_VERSION:
        raise RuntimeError("数据库迁移脚本不完整")
    with conn.transaction():
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
        applied = {
            row[0] for row in conn.execute(
                "SELECT version FROM schema_migrations"
            ).fetchall()
        }
        for migration in migration_files:
            version = migration.stem
            if version in applied:
                print(f"已应用数据库迁移：{version}")
                continue
            conn.execute(migration.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (version,))
            print(f"数据库迁移完成：{version}")


def import_records(conn, entries: list[ConvertedPoem]) -> tuple[int, int]:
    """Idempotent append only; fail on source ID/order/content drift, rollback."""
    from psycopg.types.json import Jsonb

    inserted = 0
    with conn.transaction():
        existing = {
            row[0]: (row[1], row[2])
            for row in conn.execute(
                "SELECT s.source_record_id, s.source_sha256, p.source_order "
                "FROM poem_source_texts s JOIN poems p ON p.id = s.poem_id"
            ).fetchall()
        }
        used_orders = {order: key for key, (_, order) in existing.items()}
        for entry in entries:
            p, s = entry.reader, entry.source
            key, order = p["source_record_id"], p["source_order"]
            if key in existing:
                previous_hash, previous_order = existing[key]
                if previous_hash != s["source_sha256"] or previous_order != order:
                    raise ValueError(
                        f"{key}: 来源内容或排序已变化；事务已回滚，"
                        "须人工核实原始作品位置（Issue #62）"
                    )
                continue
            if order in used_orders:
                raise ValueError(
                    f"作品位置 {order} 原属于 {used_orders[order]}；"
                    "疑似重新抽取造成 ID 漂移，事务已回滚"
                )
            poem_id = uuid.uuid4()
            conn.execute(
                """INSERT INTO poems (
                    id, source_record_id, source_order, collection, author,
                    cipai, title, yusheng_title, body_segments, prefaces, inline_notes,
                    lacunae, review_status, text_version
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )""",
                (poem_id, key, order, p["collection"], p["author"], p["cipai"],
                 p["title"], p["yusheng_title"], Jsonb(p["body_segments"]),
                 Jsonb(p["prefaces"]), Jsonb(p["inline_notes"]),
                 Jsonb(p["lacunae"]), p["review_status"], p["text_version"]),
            )
            conn.execute(
                """INSERT INTO poem_source_texts (
                    poem_id, source_record_id, source_title, source_edition,
                    source_locator, original_segments, original_inline_notes,
                    source_sha256
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (poem_id, key, s["source_title"], s["source_edition"],
                 Jsonb(s["source_locator"]) if s["source_locator"] is not None else None,
                 Jsonb(s["original_segments"]), Jsonb(s["original_inline_notes"]),
                 s["source_sha256"]),
            )
            used_orders[order] = key
            inserted += 1
    return inserted, len(entries) - inserted


def main() -> None:
    parser = argparse.ArgumentParser(description="Poeticus 本地私人词库导入")
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--check", action="store_true", help="不连接数据库")
    modes.add_argument("--migrate", action="store_true", help="执行尚未应用的数据库结构迁移")
    modes.add_argument("--import", dest="do_import", action="store_true", help="事务导入词库")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    args = parser.parse_args()
    if args.check or args.do_import:
        records = read_corpus(args.input)
        actions = Counter(a for record in records for a in record.actions)
        print(f"作品 {len(records)} 首；正文转换 {dict(actions)}")
        print(
            f"行内注记 {sum(len(r.reader['inline_notes']) for r in records)} 条；"
            f"缺文标记 {sum(len(r.reader['lacunae']) for r in records)} 条"
        )
        if args.check:
            return

    from dotenv import load_dotenv
    load_dotenv()
    dsn = os.getenv("POETICUS_DATABASE_URL")
    if not dsn:
        raise SystemExit("请在私人 .env 文件中设置 POETICUS_DATABASE_URL")
    import psycopg
    with psycopg.connect(dsn, autocommit=True) as conn:
        if args.migrate:
            migrate(conn)
        else:
            if not conn.execute(
                "SELECT 1 FROM schema_migrations WHERE version = %s",
                (LATEST_VERSION,),
            ).fetchone():
                raise SystemExit("数据库结构尚未更新；请先运行 --migrate")
            added, skipped = import_records(conn, records)
            print(f"导入完成：新增 {added} 首；已存在且一致 {skipped} 首")


if __name__ == "__main__":
    main()
