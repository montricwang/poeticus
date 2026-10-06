"""画像私人词集中的 annotations / commentaries，帮助挑选 Eval Case。

脚本只读取本地 normalized JSON；报告默认写入 data/reports/，
该目录已被 Git 忽略。报告会包含少量截断后的原书派生文本，
不要提交到公开仓库。
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "data" / "output" / "all_normalized.json"
DEFAULT_JSON_OUTPUT = ROOT / "data" / "reports" / "eval_editorial_profile.json"
DEFAULT_MD_OUTPUT = ROOT / "data" / "reports" / "eval_editorial_profile.md"

CATEGORIES = ("annotations", "commentaries")
LENGTH_BUCKETS = (
    (0, 20, "1–20"),
    (21, 50, "21–50"),
    (51, 100, "51–100"),
    (101, 200, "101–200"),
    (201, 500, "201–500"),
    (501, None, "501+"),
)


def load_records(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("normalized JSON 顶层必须是数组")
    return data


def nearest_rank(values: list[int], percentile: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(percentile * len(ordered)))
    return ordered[rank - 1]


def numeric_stats(values: list[int]) -> dict[str, float | int | None]:
    if not values:
        return {
            "min": None,
            "median": None,
            "mean": None,
            "p90": None,
            "max": None,
        }
    return {
        "min": min(values),
        "median": statistics.median(values),
        "mean": round(statistics.fmean(values), 2),
        "p90": nearest_rank(values, 0.9),
        "max": max(values),
    }


def normalize_for_duplicate(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def text_features(text: str) -> dict[str, bool]:
    return {
        "contains_colon": "：" in text or ":" in text,
        "contains_book_title_marks": "《" in text and "》" in text,
        "contains_chinese_quotes": any(mark in text for mark in ("「", "」", "“", "”")),
        "contains_newline": "\n" in text,
        "contains_digits": bool(re.search(r"\d", text)),
    }


def length_bucket(length: int) -> str:
    for low, high, label in LENGTH_BUCKETS:
        if length >= low and (high is None or length <= high):
            return label
    raise AssertionError("未匹配长度桶")


def excerpt(text: str, limit: int) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= limit:
        return compact
    return compact[:limit] + "…"


def item_metadata(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "record_id": record.get("id"),
        "author": record.get("author"),
        "collection": record.get("collection"),
        "cipai": record.get("cipai") or record.get("tune"),
        "title": record.get("title"),
    }


def collect_category(
    records: list[dict[str, Any]],
    category: str,
) -> tuple[list[dict[str, Any]], list[int], list[dict[str, Any]]]:
    items: list[dict[str, Any]] = []
    counts: list[int] = []
    anomalies: list[dict[str, Any]] = []

    for index, record in enumerate(records):
        if not isinstance(record, dict):
            counts.append(0)
            anomalies.append(
                {
                    "record_index": index,
                    "record_id": None,
                    "category": category,
                    "problem": "record_not_object",
                }
            )
            continue

        record_id = record.get("id")
        content = record.get("content")

        if not isinstance(content, dict):
            counts.append(0)
            anomalies.append(
                {
                    "record_index": index,
                    "record_id": record_id,
                    "category": category,
                    "problem": "content_not_object",
                }
            )
            continue

        raw_items = content.get(category, [])
        if not isinstance(raw_items, list):
            counts.append(0)
            anomalies.append(
                {
                    "record_index": index,
                    "record_id": record_id,
                    "category": category,
                    "problem": "category_not_array",
                    "actual_type": type(raw_items).__name__,
                }
            )
            continue

        valid_count = 0
        for item_index, raw in enumerate(raw_items):
            if not isinstance(raw, str):
                anomalies.append(
                    {
                        "record_index": index,
                        "record_id": record_id,
                        "category": category,
                        "item_index": item_index,
                        "problem": "item_not_string",
                        "actual_type": type(raw).__name__,
                    }
                )
                continue

            text = raw.strip()
            if not text:
                anomalies.append(
                    {
                        "record_index": index,
                        "record_id": record_id,
                        "category": category,
                        "item_index": item_index,
                        "problem": "empty_item",
                    }
                )
                continue

            valid_count += 1
            items.append(
                {
                    **item_metadata(record),
                    "item_index": item_index,
                    "text": text,
                    "length": len(text),
                }
            )

        counts.append(valid_count)

    return items, counts, anomalies


def aggregate_group(
    items: list[dict[str, Any]],
    key: str,
    limit: int = 30,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[int]] = defaultdict(list)
    for item in items:
        value = item.get(key)
        name = value if isinstance(value, str) and value.strip() else "（缺失）"
        grouped[name].append(item["length"])

    rows = [
        {
            key: name,
            "items": len(lengths),
            "median_length": statistics.median(lengths),
        }
        for name, lengths in grouped.items()
    ]
    rows.sort(key=lambda row: (-row["items"], str(row[key])))
    return rows[:limit]


def sample_items(
    items: list[dict[str, Any]],
    *,
    sample_size: int,
    excerpt_chars: int,
    seed: int,
) -> dict[str, list[dict[str, Any]]]:
    if not items:
        return {"shortest": [], "longest": [], "random": []}

    def public_item(item: dict[str, Any]) -> dict[str, Any]:
        return {
            key: item.get(key)
            for key in (
                "record_id",
                "author",
                "collection",
                "cipai",
                "title",
                "item_index",
                "length",
            )
        } | {"excerpt": excerpt(item["text"], excerpt_chars)}

    by_length = sorted(items, key=lambda item: (item["length"], str(item.get("record_id"))))
    shortest = by_length[:sample_size]
    longest = list(reversed(by_length[-sample_size:]))

    rng = random.Random(seed)
    random_sample = rng.sample(items, k=min(sample_size, len(items)))

    return {
        "shortest": [public_item(item) for item in shortest],
        "longest": [public_item(item) for item in longest],
        "random": [public_item(item) for item in random_sample],
    }


def profile_category(
    records: list[dict[str, Any]],
    category: str,
    *,
    sample_size: int,
    excerpt_chars: int,
    seed: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    items, counts, anomalies = collect_category(records, category)
    lengths = [item["length"] for item in items]
    duplicate_counter = Counter(
        normalize_for_duplicate(item["text"])
        for item in items
    )
    repeated = [
        {
            "count": count,
            "length": len(text),
            "excerpt": excerpt(text, excerpt_chars),
        }
        for text, count in duplicate_counter.most_common()
        if count > 1
    ][:20]

    feature_counts = Counter()
    bucket_counts = Counter()
    for item in items:
        bucket_counts[length_bucket(item["length"])] += 1
        for name, present in text_features(item["text"]).items():
            if present:
                feature_counts[name] += 1

    item_count = len(items)

    return (
        {
            "record_count": len(records),
            "records_with_items": sum(1 for count in counts if count > 0),
            "records_without_items": sum(1 for count in counts if count == 0),
            "coverage_rate": (
                round(sum(1 for count in counts if count > 0) / len(records), 4)
                if records
                else 0
            ),
            "item_count": item_count,
            "unique_item_count": len(duplicate_counter),
            "items_per_record": numeric_stats(counts),
            "item_length": numeric_stats(lengths),
            "length_buckets": {
                label: bucket_counts[label]
                for _, _, label in LENGTH_BUCKETS
            },
            "features": {
                name: {
                    "count": count,
                    "rate": round(count / item_count, 4) if item_count else 0,
                }
                for name, count in sorted(feature_counts.items())
            },
            "by_collection": aggregate_group(items, "collection"),
            "by_author": aggregate_group(items, "author"),
            "repeated_items": repeated,
            "samples": sample_items(
                items,
                sample_size=sample_size,
                excerpt_chars=excerpt_chars,
                seed=seed,
            ),
        },
        anomalies,
    )


def safe_source_label(path: Path) -> str:
    """报告里避免无意写入本机绝对路径。"""
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return path.name


def build_profile(
    records: list[dict[str, Any]],
    *,
    source_path: Path,
    sample_size: int,
    excerpt_chars: int,
    seed: int,
) -> dict[str, Any]:
    categories = {}
    anomalies = []

    for offset, category in enumerate(CATEGORIES):
        profile, category_anomalies = profile_category(
            records,
            category,
            sample_size=sample_size,
            excerpt_chars=excerpt_chars,
            seed=seed + offset,
        )
        categories[category] = profile
        anomalies.extend(category_anomalies)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_path": safe_source_label(source_path),
        "record_count": len(records),
        "sample_size": sample_size,
        "excerpt_chars": excerpt_chars,
        "seed": seed,
        "anomaly_count": len(anomalies),
        "anomalies": anomalies[:100],
        "categories": categories,
    }


def _md_table(rows: list[list[Any]], headers: list[str]) -> list[str]:
    output = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        output.append(
            "| "
            + " | ".join(
                str(value).replace("|", "\\|").replace("\n", " ")
                for value in row
            )
            + " |"
        )
    return output


def render_markdown(profile: dict[str, Any]) -> str:
    lines = [
        "# Editorial Notes Profile",
        "",
        "> 私人诊断报告。包含商业出版物的少量截断派生文本，不要提交到公开仓库。",
        "",
        f"- 作品记录：{profile['record_count']}",
        f"- 结构异常：{profile['anomaly_count']}",
        f"- 抽样 seed：{profile['seed']}",
        "",
    ]

    for category in CATEGORIES:
        data = profile["categories"][category]
        lines.extend(
            [
                f"## {category}",
                "",
                f"- 有内容的作品：{data['records_with_items']} / {data['record_count']} "
                f"（{data['coverage_rate']:.1%}）",
                f"- 元素总数：{data['item_count']}",
                f"- 去重后元素：{data['unique_item_count']}",
                f"- 每首数量：median {data['items_per_record']['median']}，"
                f"p90 {data['items_per_record']['p90']}，max {data['items_per_record']['max']}",
                f"- 元素长度：median {data['item_length']['median']}，"
                f"p90 {data['item_length']['p90']}，max {data['item_length']['max']}",
                "",
                "### 长度分布",
                "",
            ]
        )
        lines.extend(
            _md_table(
                [[label, count] for label, count in data["length_buckets"].items()],
                ["字符数", "元素数"],
            )
        )

        lines.extend(["", "### 文本特征", ""])
        feature_rows = [
            [name, value["count"], f"{value['rate']:.1%}"]
            for name, value in data["features"].items()
        ]
        if feature_rows:
            lines.extend(_md_table(feature_rows, ["特征", "数量", "占比"]))
        else:
            lines.append("无。")

        lines.extend(["", "### 按词集", ""])
        lines.extend(
            _md_table(
                [
                    [row["collection"], row["items"], row["median_length"]]
                    for row in data["by_collection"]
                ],
                ["词集", "元素数", "长度中位数"],
            )
        )

        if data["repeated_items"]:
            lines.extend(["", "### 重复元素（前 20）", ""])
            lines.extend(
                _md_table(
                    [
                        [row["count"], row["length"], row["excerpt"]]
                        for row in data["repeated_items"]
                    ],
                    ["重复次数", "长度", "文本摘录"],
                )
            )

        for sample_kind, title in (
            ("random", "随机样本"),
            ("shortest", "最短样本"),
            ("longest", "最长样本"),
        ):
            lines.extend(["", f"### {title}", ""])
            sample_rows = []
            for item in data["samples"][sample_kind]:
                identity = " / ".join(
                    str(value)
                    for value in (
                        item.get("author"),
                        item.get("cipai"),
                        item.get("title"),
                    )
                    if value
                )
                sample_rows.append(
                    [
                        item.get("record_id"),
                        identity or "（无题名）",
                        item["length"],
                        item["excerpt"],
                    ]
                )
            if sample_rows:
                lines.extend(
                    _md_table(sample_rows, ["record_id", "作品", "长度", "文本摘录"])
                )
            else:
                lines.append("无。")

        lines.append("")

    if profile["anomaly_count"]:
        lines.extend(
            [
                "## 结构异常",
                "",
                f"共 {profile['anomaly_count']} 项；JSON 报告最多保留前 100 项明细。",
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="画像 normalized JSON 中的 annotations / commentaries"
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    parser.add_argument("--sample-size", type=int, default=8)
    parser.add_argument("--excerpt-chars", type=int, default=240)
    parser.add_argument("--seed", type=int, default=20261006)
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.sample_size < 1:
        raise SystemExit("--sample-size 必须 >= 1")
    if args.excerpt_chars < 20:
        raise SystemExit("--excerpt-chars 必须 >= 20")

    records = load_records(args.input)
    profile = build_profile(
        records,
        source_path=args.input,
        sample_size=args.sample_size,
        excerpt_chars=args.excerpt_chars,
        seed=args.seed,
    )

    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.md_output.parent.mkdir(parents=True, exist_ok=True)

    args.json_output.write_text(
        json.dumps(profile, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.md_output.write_text(render_markdown(profile), encoding="utf-8")

    print(
        f"作品 {profile['record_count']}；"
        f"annotations {profile['categories']['annotations']['item_count']}；"
        f"commentaries {profile['categories']['commentaries']['item_count']}；"
        f"结构异常 {profile['anomaly_count']}"
    )
    print(f"JSON：{args.json_output}")
    print(f"Markdown：{args.md_output}")
    print("注意：报告包含少量私人出版物派生文本，不要提交公开仓库。")


if __name__ == "__main__":
    main()
