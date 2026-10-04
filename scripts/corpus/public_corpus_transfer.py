"""Transfer the *reader table only* from private local PG to Railway PG.

Data flows directly from one database connection to the other on the USER's
machine. No source EPUB, JSON export, evidence table, notes, or credentials are
written to files or GitHub. An explicit confirmation is required for writes.

PowerShell:
  python -m scripts.corpus.public_corpus_transfer --check
  # Create an authenticated Railway CLI SSH tunnel separately, then set
  # POETICUS_PUBLIC_TARGET_URL in this terminal (never paste it into chat).
  python -m scripts.corpus.public_corpus_transfer --apply --confirm-publish
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections import Counter
from uuid import UUID

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

# Explicitly whitelisted, current HTTP reader fields + stable internal keys.
# Excludes poem_source_texts, original_segments, original_inline_notes,
# source_locator, inline_notes, lacunae, modern annotations and commentary.
PUBLIC_COLUMNS = (
    "id", "source_record_id", "source_order", "collection", "author",
    "cipai", "title", "yusheng_title", "body_segments", "prefaces",
    "review_status", "text_version",
)
SELECT_PUBLIC = "SELECT " + ", ".join(PUBLIC_COLUMNS) + " FROM poems ORDER BY source_order"
INSERT_PUBLIC = (
    "INSERT INTO poems (" + ", ".join(PUBLIC_COLUMNS) + ") VALUES ("
    + ", ".join(["%s"] * len(PUBLIC_COLUMNS)) + ")"
)

# Exact identifiers from our intentionally synthetic cloud seed.
DEMO_IDS = {
    UUID("00000000-0000-4000-8000-000000000101"): "demo-synthetic-1",
    UUID("00000000-0000-4000-8000-000000000102"): "demo-synthetic-2",
    UUID("00000000-0000-4000-8000-000000000103"): "demo-synthetic-3",
}
# Heuristic only, not a determination of literary copyright/attribution.
SUSPECT_EDITORIAL = re.compile(
    r"编者按|出版社|本书编|责任编辑|现代汉语译|校注者|译文|赏析|鉴赏辞典"
)


def public_fingerprint(rows: list[dict]) -> str:
    """A reproducible full-content checksum; print hashes, never actual texts."""
    payload = [{key: row[key] for key in PUBLIC_COLUMNS} for row in rows]
    packed = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(packed.encode("utf-8")).hexdigest()


def validate_public_rows(rows: list[dict], expected: int) -> dict:
    if len(rows) != expected:
        raise ValueError(f"读取 {len(rows)} 首，预期 {expected} 首；停止操作")
    ids, source_ids, orders = set(), set(), set()
    review_states = Counter()
    preface_count = 0
    suspect_records = []
    max_segment_chars = 0
    for row in rows:
        if set(row) != set(PUBLIC_COLUMNS):
            raise ValueError("读取字段不是明确允许公开的列集合")
        if not isinstance(row["id"], UUID):
            raise ValueError("作品 UUID 字段类型异常")
        if row["id"] in ids or row["source_record_id"] in source_ids or row["source_order"] in orders:
            raise ValueError("出现重复 UUID / source_record_id / source_order")
        ids.add(row["id"])
        source_ids.add(row["source_record_id"])
        orders.add(row["source_order"])
        if row["source_order"] < 1 or row["text_version"] < 1:
            raise ValueError("排序或文本版本无效")
        body, prefaces = row["body_segments"], row["prefaces"]
        if not isinstance(body, list) or not body or any(not isinstance(s, str) for s in body):
            raise ValueError("正文必须是非空字符串数组")
        if not any(piece.strip() for piece in body):
            raise ValueError("正文不能为空白")
        if not isinstance(prefaces, list) or any(not isinstance(s, str) for s in prefaces):
            raise ValueError("词序必须是字符串数组")
        max_segment_chars = max(max_segment_chars, *(len(s) for s in body))
        preface_count += len(prefaces)
        review_states[row["review_status"]] += 1
        if any(SUSPECT_EDITORIAL.search(s) for s in body + prefaces):
            suspect_records.append(row["source_order"])
    if orders != set(range(1, expected + 1)):
        raise ValueError("原书排序并非完整的 1..N；请先调查，不自动重排")
    return {
        "rows": len(rows), "prefaces": preface_count,
        "review_states": dict(review_states),
        "max_segment_chars": max_segment_chars,
        "suspect_editorial_count": len(suspect_records),
        "suspect_source_orders": suspect_records[:15],
        "sha256": public_fingerprint(rows),
    }


def _is_exact_demo(row: dict) -> bool:
    return (
        row["id"] in DEMO_IDS
        and row["source_record_id"] == DEMO_IDS[row["id"]]
        and row["collection"] == "Poeticus 合成测试作品"
        and row["review_status"] == "demo_synthetic"
    )


def transfer(source: list[dict], dest_conn: psycopg.Connection) -> str:
    """Atomic swap of known demo rows, or idempotent check of prior full copy.

    Reject any unexpected target content instead of deleting or overwriting it.
    """
    with dest_conn.transaction():
        dest_rows = dest_conn.execute(SELECT_PUBLIC).fetchall()
        if dest_rows and all(_is_exact_demo(r) for r in dest_rows):
            if len(dest_rows) != len({r["id"] for r in dest_rows}):
                raise ValueError("云端测试数据 UUID 重复")
            demo_ids = list(DEMO_IDS)
            dest_conn.execute(
                "DELETE FROM poems WHERE id = ANY(%s)", (demo_ids,)
            )
            result = "replaced_known_demo"
        elif dest_rows and public_fingerprint(dest_rows) == public_fingerprint(source):
            return "already_identical"
        elif dest_rows:
            raise ValueError("目标库含非预期数据；拒绝覆盖或清空，请先检查")
        else:
            result = "inserted_into_empty"

        for row in source:
            values = [
                Jsonb(row[k]) if k in ("body_segments", "prefaces") else row[k]
                for k in PUBLIC_COLUMNS
            ]
            dest_conn.execute(INSERT_PUBLIC, values)

        after = dest_conn.execute(SELECT_PUBLIC).fetchall()
        if public_fingerprint(after) != public_fingerprint(source):
            raise ValueError("云端内容与源库不一致；事务回滚")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="全量私有 PG → 云端公开阅读表（不导出来源证据）")
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--check", action="store_true", help="只读统计，不连接云端")
    modes.add_argument("--apply", action="store_true", help="事务迁入云端")
    parser.add_argument("--expect-count", type=int, default=3491)
    parser.add_argument("--confirm-publish", action="store_true", help="已审核作品公开范围")
    args = parser.parse_args()
    if args.expect_count < 1:
        parser.error("--expect-count 必须大于 0")
    if args.apply and not args.confirm_publish:
        parser.error("--apply 需要 --confirm-publish 以确认公开作品字段")

    load_dotenv()
    source_dsn = os.getenv("POETICUS_DATABASE_URL")
    if not source_dsn:
        parser.error("本地 POETICUS_DATABASE_URL 未设置")
    target_dsn = os.getenv("POETICUS_PUBLIC_TARGET_URL") if args.apply else None
    if args.apply and not target_dsn:
        parser.error("未设置 POETICUS_PUBLIC_TARGET_URL；请先通过 Railway SSH tunnel 连接")
    if target_dsn and target_dsn == source_dsn:
        parser.error("源库与目标库连接字符串相同，拒绝操作")

    with psycopg.connect(source_dsn, row_factory=dict_row) as local:
        local.execute("SET TRANSACTION READ ONLY")
        rows = local.execute(SELECT_PUBLIC).fetchall()
        report = validate_public_rows(rows, args.expect_count)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if args.check:
            print("完成只读预检：没有生成或上传包含原文的文件。")
            return

        with psycopg.connect(target_dsn, row_factory=dict_row, autocommit=True) as target:
            outcome = transfer(rows, target)
            print(f"云端事务完成：{outcome}；作品 {len(rows)} 首；校验 SHA-256 一致。")


if __name__ == "__main__":
    main()
