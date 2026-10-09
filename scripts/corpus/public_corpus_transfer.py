"""只把私人 PostgreSQL 的阅读表公开字段传到 Railway PostgreSQL。

数据直接从本机一个数据库连接流向另一个连接，不生成 EPUB、JSON、证据表、
注释或凭据文件。写入前必须显式确认。

Git Bash 用法：
  # 另开终端保持 Railway 的认证 SSH 隧道运行：
  # railway connect Postgres --tunnel-only -P 55432
  python -m scripts.corpus.public_corpus_transfer --check
  python -m scripts.corpus.public_corpus_transfer --apply --confirm-publish
  # --apply 在未设置目标 URL 时会提示粘贴 SSH 隧道地址。
  # 地址会显示在终端中，因此终端和截图都应保持私密。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from uuid import UUID

import psycopg
from dotenv import load_dotenv
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import DictRow, dict_row
from psycopg.types.json import Jsonb

# 明确列出允许公开的阅读字段与稳定内部键。
# 不包含 poem_source_texts、原始片段、行内注记、缺文、现代注评等私人字段。
PUBLIC_COLUMNS = (
    "id", "source_record_id", "source_order", "collection", "author",
    "cipai", "title", "yusheng_title", "body_segments", "prefaces",
    "review_status", "text_version",
)
SELECT_PUBLIC = "SELECT " + ", ".join(PUBLIC_COLUMNS) + " FROM poems ORDER BY source_order"
COPY_PUBLIC = "COPY poems (" + ", ".join(PUBLIC_COLUMNS) + ") FROM STDIN"

# 这里只做启发式排查，不代表对文学版权或文本归属作出判断。
SUSPECT_EDITORIAL = re.compile(
    r"编者按|出版社|本书编|责任编辑|现代汉语译|校注者|译文|赏析|鉴赏辞典"
)


def public_fingerprint(rows: Sequence[Mapping[str, object]]) -> str:
    """计算可重复的全量内容摘要；只输出哈希，不输出实际正文。"""
    payload = [{key: row[key] for key in PUBLIC_COLUMNS} for row in rows]
    packed = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(packed.encode("utf-8")).hexdigest()


def validate_public_rows(rows: Sequence[Mapping[str, object]], expected: int) -> dict[str, object]:
    if len(rows) != expected:
        raise ValueError(f"读取 {len(rows)} 首，预期 {expected} 首；停止操作")
    ids: set[UUID] = set()
    source_ids: set[str] = set()
    orders: set[int] = set()
    review_states: Counter[str] = Counter()
    preface_count = 0
    suspect_records: list[int] = []
    max_segment_chars = 0
    for row in rows:
        if set(row) != set(PUBLIC_COLUMNS):
            raise ValueError("读取字段不是明确允许公开的列集合")
        work_id = row["id"]
        source_id = row["source_record_id"]
        source_order = row["source_order"]
        text_version = row["text_version"]
        review_status = row["review_status"]
        if not isinstance(work_id, UUID):
            raise ValueError("作品 UUID 字段类型异常")
        if (not isinstance(source_id, str) or
                not isinstance(source_order, int) or isinstance(source_order, bool) or
                not isinstance(text_version, int) or isinstance(text_version, bool) or
                not isinstance(review_status, str)):
            raise ValueError("公开作品的编号、版本或审核状态字段类型异常")
        if work_id in ids or source_id in source_ids or source_order in orders:
            raise ValueError("出现重复 UUID / source_record_id / source_order")
        ids.add(work_id)
        source_ids.add(source_id)
        orders.add(source_order)
        if source_order < 1 or text_version < 1:
            raise ValueError("排序或文本版本无效")
        body, prefaces = row["body_segments"], row["prefaces"]
        if not isinstance(body, list) or not body or any(not isinstance(s, str) for s in body):
            raise ValueError("正文必须是非空字符串数组")
        if not isinstance(prefaces, list) or any(not isinstance(s, str) for s in prefaces):
            raise ValueError("词序必须是字符串数组")
        text_segments = [piece for piece in body if isinstance(piece, str)]
        preface_segments = [piece for piece in prefaces if isinstance(piece, str)]
        if not any(piece.strip() for piece in text_segments):
            raise ValueError("正文不能为空白")
        max_segment_chars = max(max_segment_chars, *(len(s) for s in text_segments))
        preface_count += len(preface_segments)
        review_states[review_status] += 1
        if any(SUSPECT_EDITORIAL.search(s) for s in text_segments + preface_segments):
            suspect_records.append(source_order)
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


def transfer(source: Sequence[Mapping[str, object]], dest_conn: psycopg.Connection[DictRow]) -> str:
    """单事务、单 COPY 流传输，并对源目标做全量一致性校验。

    目标库存在未知内容时拒绝覆盖；提交前中断会回滚。
    如果上一次提交结果不确定，重复执行会识别完全一致的数据。
    """
    expected_digest = public_fingerprint(source)
    print("检查云端现有作品……", flush=True)
    with dest_conn.transaction():
        dest_conn.execute("SET LOCAL lock_timeout = '15s'")
        dest_conn.execute("SET LOCAL statement_timeout = '180s'")
        dest_rows = dest_conn.execute(SELECT_PUBLIC).fetchall()
        if dest_rows and public_fingerprint(dest_rows) == expected_digest:
            print("云端作品已经与本地完全一致，无需重复导入。", flush=True)
            return "already_identical"
        elif dest_rows:
            raise ValueError("目标库含非预期数据；拒绝覆盖或清空，请先检查")
        else:
            result = "inserted_into_empty"

        print(f"开始 PostgreSQL COPY 批量传输，共 {len(source)} 首……", flush=True)
        with dest_conn.cursor() as cursor:
            with cursor.copy(COPY_PUBLIC) as copy:
                for i, row in enumerate(source, 1):
                    values = [
                        Jsonb(row[k]) if k in ("body_segments", "prefaces") else row[k]
                        for k in PUBLIC_COLUMNS
                    ]
                    copy.write_row(values)
                    if i % 500 == 0 or i == len(source):
                        print(f"  已送入 COPY：{i}/{len(source)} 首", flush=True)

        print("批量传输结束，读取云端核对所有公开列……", flush=True)
        after = dest_conn.execute(SELECT_PUBLIC).fetchall()
        if public_fingerprint(after) != expected_digest:
            raise ValueError("云端内容与源库不一致；事务回滚")
        print("全量 SHA-256 一致，正在提交事务……", flush=True)
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
        print("请粘贴 Railway SSH 隧道输出的 PostgreSQL URL（会在终端显示；勿发聊天）。", flush=True)
        target_dsn = input("Railway PostgreSQL URL: ").strip()
    if args.apply and not target_dsn:
        parser.error("没有输入目标连接 URL")
    if target_dsn:
        if target_dsn == source_dsn:
            parser.error("源库与目标库连接字符串相同，拒绝操作")
        # 这里只接受 Railway CLI 建立的本地隧道，不接受公网 PostgreSQL 地址。
        try:
            info = conninfo_to_dict(target_dsn)
        except psycopg.Error:
            parser.error("目标数据库 URL 格式不正确")
        host, port = info.get("host"), str(info.get("port", ""))
        if host not in ("127.0.0.1", "localhost") or port != "55432":
            parser.error("目标必须是 Railway CLI 本地 SSH 隧道 127.0.0.1:55432，拒绝其他地址")

    print("读取并检查本地作品……", flush=True)
    with psycopg.Connection[DictRow].connect(source_dsn, row_factory=dict_row, connect_timeout=10) as local:
        local.execute("SET TRANSACTION READ ONLY")
        rows = local.execute(SELECT_PUBLIC).fetchall()
        report = validate_public_rows(rows, args.expect_count)
        print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
        if args.check:
            print("完成只读预检：没有生成或上传包含原文的文件。")
            return

        print("连接 Railway（超时 10 秒，保持 SSH 隧道窗口开启）……", flush=True)
        if not target_dsn:
            parser.error("没有输入目标连接 URL")
        with psycopg.Connection[DictRow].connect(target_dsn, row_factory=dict_row, autocommit=True, connect_timeout=10) as target:
            print("已连接云端 PostgreSQL。", flush=True)
            outcome = transfer(rows, target)
            print(f"云端事务完成：{outcome}；作品 {len(rows)} 首；校验 SHA-256 一致。", flush=True)


if __name__ == "__main__":
    try:
        main()
    except psycopg.Error as exc:
        # libpq 的原始错误详情可能暴露网络或内部配置，因此不直接回显。
        raise SystemExit(
            f"数据库操作失败（{type(exc).__name__}）；未提交的事务会回滚。"
            "请确认 Railway SSH 隧道仍在运行、端口正确。"
        ) from None
