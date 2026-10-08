"""从私人 annotations 中抽取一小批 Eval 候选。

这是 2026-10-06 14:50 的诊断脚本版本。它只做候选筛选：
- 词头 + 冒号，并且词头能在本词正文直接找到；
- 带明确尾部来源的前人引文。

脚本不自动把这些候选解释成“词义”“典故”或“化用”。
输出位于 poeticus-data/reports/evals/，包含商业出版物派生文本，不得提交公开仓库。
"""

from __future__ import annotations

import argparse
import json
import random
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from backend.data_paths import EVAL_REPORTS_ROOT, READING_NORMALIZED_ROOT
from typing import Any

from scripts.evals.profile_editorial_notes import (
    ROOT,
    TRAILING_SOURCE,
    classify_annotation_structure,
    collect_category,
    excerpt,
    load_records,
    normalize_for_duplicate,
    safe_source_label,
)


STAMP = "10061450"
DEFAULT_INPUT = READING_NORMALIZED_ROOT / "all_normalized.json"
DEFAULT_JSON_OUTPUT = EVAL_REPORTS_ROOT / f"eval_candidates_{STAMP}.json"
DEFAULT_MD_OUTPUT = EVAL_REPORTS_ROOT / f"eval_candidates_{STAMP}.md"


def compact_poem(record: dict[str, Any], limit: int = 360) -> str:
    content = record.get("content")
    if not isinstance(content, dict):
        return ""
    pieces = content.get("text", [])
    if not isinstance(pieces, list):
        return ""
    text = " / ".join(
        re.sub(r"\s+", " ", piece).strip()
        for piece in pieces
        if isinstance(piece, str) and piece.strip()
    )
    return excerpt(text, limit)


def source_hint(text: str) -> str | None:
    match = TRAILING_SOURCE.search(text)
    if not match:
        return None
    return match.group(0).strip()


def dedupe_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result = []
    for item in items:
        key = normalize_for_duplicate(item["text"])
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def balanced_sample(
    items: list[dict[str, Any]],
    *,
    limit: int,
    seed: int,
) -> list[dict[str, Any]]:
    """在词集之间轮转抽样，避免大词集淹没候选池。"""
    if limit <= 0 or not items:
        return []

    rng = random.Random(seed)
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        collection = item.get("collection")
        key = collection if isinstance(collection, str) and collection else "（缺失）"
        groups[key].append(item)

    names = sorted(groups)
    rng.shuffle(names)
    for name in names:
        rng.shuffle(groups[name])

    selected: list[dict[str, Any]] = []
    while len(selected) < limit:
        progressed = False
        for name in names:
            bucket = groups[name]
            if not bucket:
                continue
            selected.append(bucket.pop())
            progressed = True
            if len(selected) >= limit:
                break
        if not progressed:
            break

    return selected


def candidate_record(
    item: dict[str, Any],
    record: dict[str, Any],
    *,
    kind: str,
) -> dict[str, Any]:
    base = {
        "candidate_id": f"{kind}_{item['record_id']}_{item['item_index']}",
        "kind": kind,
        "record_id": item.get("record_id"),
        "author": item.get("author"),
        "collection": item.get("collection"),
        "cipai": item.get("cipai"),
        "title": item.get("title"),
        "poem_excerpt": compact_poem(record),
        "annotation": item["text"],
        "annotation_length": item["length"],
    }

    if kind == "headword_colon":
        base.update(
            {
                "headword": item.get("headword"),
                "suggested_question": (
                    f"「{item.get('headword')}」在这里是什么意思？"
                    if item.get("headword")
                    else None
                ),
                "contains_book_title_marks": "《" in item["text"] and "》" in item["text"],
            }
        )
    elif kind == "quoted_source":
        base.update(
            {
                "source_hint": source_hint(item["text"]),
                "suggested_question": None,
            }
        )

    return base


def build_candidate_pool(
    records: list[dict[str, Any]],
    *,
    headword_limit: int,
    quoted_limit: int,
    seed: int,
) -> dict[str, Any]:
    annotations, _, anomalies = collect_category(records, "annotations")
    record_by_id = {
        record.get("id"): record
        for record in records
        if isinstance(record, dict) and isinstance(record.get("id"), str)
    }

    headword_pool: list[dict[str, Any]] = []
    quoted_pool: list[dict[str, Any]] = []

    for item in annotations:
        info = classify_annotation_structure(item)
        item.update(info)

        if (
            item["structure"] == "headword_colon"
            and item.get("headword")
            and item.get("headword_in_body") is True
        ):
            headword_pool.append(item)
        elif item["structure"] == "quoted_source":
            quoted_pool.append(item)

    headword_pool = dedupe_items(headword_pool)
    quoted_pool = dedupe_items(quoted_pool)

    selected_headword = balanced_sample(
        headword_pool,
        limit=headword_limit,
        seed=seed,
    )
    selected_quoted = balanced_sample(
        quoted_pool,
        limit=quoted_limit,
        seed=seed + 1,
    )

    def materialize(items: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
        result = []
        for item in items:
            record = record_by_id.get(item.get("record_id"))
            if not isinstance(record, dict):
                continue
            result.append(candidate_record(item, record, kind=kind))
        return result

    headword_candidates = materialize(selected_headword, "headword_colon")
    quoted_candidates = materialize(selected_quoted, "quoted_source")

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seed": seed,
        "record_count": len(records),
        "annotation_count": len(annotations),
        "anomaly_count": len(anomalies),
        "pool_stats": {
            "headword_colon_in_body_unique": len(headword_pool),
            "quoted_source_unique": len(quoted_pool),
        },
        "selection_stats": {
            "headword_colon": len(headword_candidates),
            "quoted_source": len(quoted_candidates),
            "headword_collections": dict(
                sorted(Counter(
                    candidate.get("collection") or "（缺失）"
                    for candidate in headword_candidates
                ).items())
            ),
            "quoted_source_collections": dict(
                sorted(Counter(
                    candidate.get("collection") or "（缺失）"
                    for candidate in quoted_candidates
                ).items())
            ),
        },
        "candidates": {
            "headword_colon": headword_candidates,
            "quoted_source": quoted_candidates,
        },
    }


def md_escape(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_markdown(profile: dict[str, Any], source_path: Path) -> str:
    stats = profile["pool_stats"]
    selected = profile["selection_stats"]

    lines = [
        f"# Eval Candidates {STAMP}",
        "",
        "> 私人候选报告。内容来自商业出版物的编者注，仅用于人工挑选 Eval Case，不得提交公开仓库。",
        "",
        f"- 来源：{safe_source_label(source_path)}",
        f"- 作品：{profile['record_count']}",
        f"- annotations：{profile['annotation_count']}",
        f"- 结构异常：{profile['anomaly_count']}",
        f"- 可用短词头候选（去重）：{stats['headword_colon_in_body_unique']}",
        f"- 可用引文来源候选（去重）：{stats['quoted_source_unique']}",
        f"- 本轮抽取：短词头 {selected['headword_colon']}，引文来源 {selected['quoted_source']}",
        "",
        "## 1. 短词头 + 冒号候选",
        "",
        "> 只保留词头能在本词正文直接找到的项目。它可能是词义、人物、地名、典故等，仍需人工判断。",
        "",
        "| ID | 作品 | 词头 | 注释 | 正文 |",
        "| --- | --- | --- | --- | --- |",
    ]

    for candidate in profile["candidates"]["headword_colon"]:
        identity = " / ".join(
            str(value)
            for value in (
                candidate.get("author"),
                candidate.get("cipai"),
                candidate.get("title"),
            )
            if value
        )
        lines.append(
            "| "
            + " | ".join(
                md_escape(value)
                for value in (
                    candidate["candidate_id"],
                    identity,
                    candidate.get("headword") or "",
                    excerpt(candidate["annotation"], 140),
                    candidate["poem_excerpt"],
                )
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## 2. 带尾部来源的引文候选",
            "",
            "> 这里只能说明编者在该词下注入了一段有明确出处的前人文字；是否属于直接化用、典故出处或比较材料，需要人工确认。",
            "",
            "| ID | 作品 | 来源提示 | 编者注 | 正文 |",
            "| --- | --- | --- | --- | --- |",
        ]
    )

    for candidate in profile["candidates"]["quoted_source"]:
        identity = " / ".join(
            str(value)
            for value in (
                candidate.get("author"),
                candidate.get("cipai"),
                candidate.get("title"),
            )
            if value
        )
        lines.append(
            "| "
            + " | ".join(
                md_escape(value)
                for value in (
                    candidate["candidate_id"],
                    identity,
                    candidate.get("source_hint") or "",
                    excerpt(candidate["annotation"], 180),
                    candidate["poem_excerpt"],
                )
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## 下一步人工选择",
            "",
            "先从这 60 条里挑约 20 条真正像用户会问的问题；暂不自动写入 seed_cases.json。",
            "",
            "- 词义 / 用法清楚、适合直接问「X 是什么意思」；",
            "- 容易望文生义或与现代义不同；",
            "- 需要人物、地名或典故背景；",
            "- 前人文本关系较明确，值得测试出处 / 化用能力；",
            "- 对关系本身有疑问的，保留为候选，不当作 Ground Truth。",
            "",
        ]
    )

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="从 annotations 抽取 Eval 候选")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    parser.add_argument("--headword-limit", type=int, default=30)
    parser.add_argument("--quoted-limit", type=int, default=30)
    parser.add_argument("--seed", type=int, default=20261006)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.headword_limit < 1 or args.quoted_limit < 1:
        raise SystemExit("候选数量必须 >= 1")

    records = load_records(args.input)
    profile = build_candidate_pool(
        records,
        headword_limit=args.headword_limit,
        quoted_limit=args.quoted_limit,
        seed=args.seed,
    )

    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.md_output.parent.mkdir(parents=True, exist_ok=True)

    args.json_output.write_text(
        json.dumps(profile, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.md_output.write_text(
        render_markdown(profile, args.input),
        encoding="utf-8",
    )

    stats = profile["selection_stats"]
    print(
        f"候选生成完成：短词头 {stats['headword_colon']}；"
        f"引文来源 {stats['quoted_source']}"
    )
    print(f"JSON：{args.json_output}")
    print(f"Markdown：{args.md_output}")
    print("注意：报告含私人出版物派生文本，不要提交公开仓库。")


if __name__ == "__main__":
    main()
