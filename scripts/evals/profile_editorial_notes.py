"""画像私人词集中的 annotations / commentaries，帮助挑选 Eval Case。

脚本只读取本地 normalized JSON；报告默认写入 poeticus-data/reports/evals/，
该目录已被 Git 忽略。报告会包含少量截断后的原书派生文本，
不要提交到公开仓库。

annotations 的结构分类只用于筛选候选样本，不宣称已经判断出
“词义 / 典故 / 化用”等文学语义。
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

from backend.data_paths import EVAL_REPORTS_ROOT, READING_NORMALIZED_ROOT
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = READING_NORMALIZED_ROOT / "all_normalized.json"
DEFAULT_JSON_OUTPUT = EVAL_REPORTS_ROOT / "eval_editorial_profile.json"
DEFAULT_MD_OUTPUT = EVAL_REPORTS_ROOT / "eval_editorial_profile.md"

CATEGORIES = ("annotations", "commentaries")
LENGTH_BUCKETS = (
    (0, 20, "1–20"),
    (21, 50, "21–50"),
    (51, 100, "51–100"),
    (101, 200, "101–200"),
    (201, 500, "201–500"),
    (501, None, "501+"),
)

ANNOTATION_MARKER = re.compile(r"^[◎○●◆◇※]\s*")
CROSS_REFERENCE = re.compile(r"(?:见前|见上|见后|参见|详见|见[^。；]{0,20}注)")
TRAILING_SOURCE = re.compile(r"（[^（）]{0,80}《[^》]{1,80}》[^（）]{0,40}）\s*$")
HEADWORD_MAX_CHARS = 12
LONG_NOTE_CHARS = 200
HEADWORD_FORBIDDEN = frozenset("，。；！？、“”‘’「」『』《》（）()【】[]")


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


def record_group_name(record: dict[str, Any], key: str) -> str:
    value = record.get(key)
    return value if isinstance(value, str) and value.strip() else "（缺失）"


def record_body_text(record: dict[str, Any]) -> str:
    content = record.get("content")
    if not isinstance(content, dict):
        return ""
    pieces = content.get("text", [])
    if not isinstance(pieces, list):
        return ""
    return "".join(piece for piece in pieces if isinstance(piece, str))


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
        body_text = record_body_text(record)

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
                    "_body_text": body_text,
                }
            )

        counts.append(valid_count)

    return items, counts, anomalies


def aggregate_group(
    records: list[dict[str, Any]],
    items: list[dict[str, Any]],
    key: str,
    limit: int = 30,
) -> list[dict[str, Any]]:
    record_counts = Counter()
    item_counts = Counter()
    records_with_items: dict[str, set[str]] = defaultdict(set)
    lengths: dict[str, list[int]] = defaultdict(list)

    for index, record in enumerate(records):
        if not isinstance(record, dict):
            continue
        group = record_group_name(record, key)
        record_counts[group] += 1

    for item in items:
        value = item.get(key)
        group = value if isinstance(value, str) and value.strip() else "（缺失）"
        item_counts[group] += 1
        record_id = item.get("record_id")
        records_with_items[group].add(
            str(record_id) if record_id is not None else f"missing:{id(item)}"
        )
        lengths[group].append(item["length"])

    rows = []
    for group, record_count in record_counts.items():
        count = item_counts[group]
        annotated_records = len(records_with_items[group])
        rows.append(
            {
                key: group,
                "records": record_count,
                "records_with_items": annotated_records,
                "coverage_rate": round(annotated_records / record_count, 4)
                if record_count
                else 0,
                "items": count,
                "items_per_record": round(count / record_count, 2)
                if record_count
                else 0,
                "items_per_annotated_record": round(count / annotated_records, 2)
                if annotated_records
                else 0,
                "median_length": (
                    statistics.median(lengths[group]) if lengths[group] else None
                ),
            }
        )

    rows.sort(key=lambda row: (-row["items_per_record"], -row["items"], str(row[key])))
    return rows[:limit]


def public_item(item: dict[str, Any], excerpt_chars: int) -> dict[str, Any]:
    data = {
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
    }
    data["excerpt"] = excerpt(item["text"], excerpt_chars)

    if "structure" in item:
        data["structure"] = item["structure"]
    if item.get("headword") is not None:
        data["headword"] = item["headword"]
        data["headword_in_body"] = item.get("headword_in_body")

    return data


def sample_items(
    items: list[dict[str, Any]],
    *,
    sample_size: int,
    excerpt_chars: int,
    seed: int,
) -> dict[str, list[dict[str, Any]]]:
    if not items:
        return {"shortest": [], "longest": [], "random": []}

    by_length = sorted(items, key=lambda item: (item["length"], str(item.get("record_id"))))
    shortest = by_length[:sample_size]
    longest = list(reversed(by_length[-sample_size:]))

    rng = random.Random(seed)
    random_sample = rng.sample(items, k=min(sample_size, len(items)))

    return {
        "shortest": [public_item(item, excerpt_chars) for item in shortest],
        "longest": [public_item(item, excerpt_chars) for item in longest],
        "random": [public_item(item, excerpt_chars) for item in random_sample],
    }


def extract_headword(text: str) -> str | None:
    cleaned = ANNOTATION_MARKER.sub("", text, count=1).strip()
    positions = [pos for mark in ("：", ":") if (pos := cleaned.find(mark)) >= 0]
    if not positions:
        return None

    colon = min(positions)
    headword = cleaned[:colon].strip()
    if not 1 <= len(headword) <= HEADWORD_MAX_CHARS:
        return None
    if any(char in HEADWORD_FORBIDDEN for char in headword):
        return None
    return headword


def classify_annotation_structure(item: dict[str, Any]) -> dict[str, Any]:
    text = item["text"]
    headword = extract_headword(text)

    if CROSS_REFERENCE.search(text):
        structure = "cross_reference"
    elif headword is not None:
        structure = "headword_colon"
    elif len(text) >= LONG_NOTE_CHARS:
        structure = "long_source_note"
    elif TRAILING_SOURCE.search(text):
        structure = "quoted_source"
    else:
        structure = "other"

    result: dict[str, str | bool] = {"structure": structure}
    if headword is not None:
        result["headword"] = headword
        result["headword_in_body"] = headword in item.get("_body_text", "")
    return result


def profile_annotation_structures(
    items: list[dict[str, Any]],
    *,
    sample_size: int,
    excerpt_chars: int,
    seed: int,
) -> dict[str, Any]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for item in items:
        item.update(classify_annotation_structure(item))
        buckets[item["structure"]].append(item)

    order = (
        "headword_colon",
        "quoted_source",
        "cross_reference",
        "long_source_note",
        "other",
    )
    counts = [
        {
            "structure": name,
            "count": len(buckets[name]),
            "rate": round(len(buckets[name]) / len(items), 4) if items else 0,
        }
        for name in order
    ]

    headword_items = [
        item
        for item in items
        if item.get("headword") is not None
    ]
    matched = [
        item
        for item in headword_items
        if item.get("headword_in_body") is True
    ]
    unmatched = [
        item
        for item in headword_items
        if item.get("headword_in_body") is False
    ]

    rng = random.Random(seed)
    samples = {}
    for name in order:
        candidates = buckets[name]
        chosen = rng.sample(candidates, k=min(sample_size, len(candidates)))
        samples[name] = [public_item(item, excerpt_chars) for item in chosen]

    return {
        "note": (
            "以下分类只按文本形态筛选候选，不代表已经判断为词义、典故或化用。"
        ),
        "counts": counts,
        "headword_candidates": {
            "count": len(headword_items),
            "matched_in_body": len(matched),
            "unmatched_in_body": len(unmatched),
            "match_rate": round(len(matched) / len(headword_items), 4)
            if headword_items
            else 0,
            "matched_samples": [
                public_item(item, excerpt_chars)
                for item in rng.sample(matched, k=min(sample_size, len(matched)))
            ],
            "unmatched_samples": [
                public_item(item, excerpt_chars)
                for item in rng.sample(unmatched, k=min(sample_size, len(unmatched)))
            ],
        },
        "samples": samples,
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
    result = {
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
        "by_collection": aggregate_group(records, items, "collection"),
        "by_author": aggregate_group(records, items, "author"),
        "repeated_items": repeated,
        "samples": sample_items(
            items,
            sample_size=sample_size,
            excerpt_chars=excerpt_chars,
            seed=seed,
        ),
    }

    if category == "annotations":
        result["structure_candidates"] = profile_annotation_structures(
            items,
            sample_size=sample_size,
            excerpt_chars=excerpt_chars,
            seed=seed + 100,
        )

    return result, anomalies


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


def _identity(item: dict[str, Any]) -> str:
    return " / ".join(
        str(value)
        for value in (
            item.get("author"),
            item.get("cipai"),
            item.get("title"),
        )
        if value
    ) or "（无题名）"


def _sample_rows(samples: list[dict[str, Any]]) -> list[list[Any]]:
    rows = []
    for item in samples:
        rows.append(
            [
                item.get("record_id"),
                _identity(item),
                item.get("headword", ""),
                (
                    ""
                    if item.get("headword_in_body") is None
                    else "是" if item["headword_in_body"] else "否"
                ),
                item["length"],
                item["excerpt"],
            ]
        )
    return rows


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

        lines.extend(["", "### 按词集（按每首元素数排序）", ""])
        lines.extend(
            _md_table(
                [
                    [
                        row["collection"],
                        row["records"],
                        row["records_with_items"],
                        f"{row['coverage_rate']:.1%}",
                        row["items"],
                        row["items_per_record"],
                        row["items_per_annotated_record"],
                        row["median_length"],
                    ]
                    for row in data["by_collection"]
                ],
                [
                    "词集",
                    "作品数",
                    "有内容作品",
                    "覆盖率",
                    "元素数",
                    "每首",
                    "有内容作品每首",
                    "长度中位数",
                ],
            )
        )

        if category == "annotations":
            structure = data["structure_candidates"]
            lines.extend(
                [
                    "",
                    "### annotation 结构候选",
                    "",
                    f"> {structure['note']}",
                    "",
                ]
            )
            lines.extend(
                _md_table(
                    [
                        [row["structure"], row["count"], f"{row['rate']:.1%}"]
                        for row in structure["counts"]
                    ],
                    ["结构", "数量", "占比"],
                )
            )

            headwords = structure["headword_candidates"]
            lines.extend(
                [
                    "",
                    "### 冒号前词头候选",
                    "",
                    f"- 候选：{headwords['count']}",
                    f"- 能在本词正文找到：{headwords['matched_in_body']} "
                    f"（{headwords['match_rate']:.1%}）",
                    f"- 未在本词正文直接找到：{headwords['unmatched_in_body']}",
                    "",
                ]
            )

            for key, title in (
                ("matched_samples", "词头命中正文样本"),
                ("unmatched_samples", "词头未命中正文样本"),
            ):
                lines.extend([f"#### {title}", ""])
                samples = headwords[key]
                if samples:
                    lines.extend(
                        _md_table(
                            _sample_rows(samples),
                            ["record_id", "作品", "词头", "正文命中", "长度", "文本摘录"],
                        )
                    )
                else:
                    lines.append("无。")
                lines.append("")

            structure_titles = {
                "headword_colon": "短词头 + 冒号",
                "quoted_source": "带尾部来源的引文",
                "cross_reference": "交叉引用",
                "long_source_note": "长篇来源/本事候选",
                "other": "其他",
            }
            for name, title in structure_titles.items():
                lines.extend([f"#### {title}样本", ""])
                samples = structure["samples"][name]
                if samples:
                    lines.extend(
                        _md_table(
                            _sample_rows(samples),
                            ["record_id", "作品", "词头", "正文命中", "长度", "文本摘录"],
                        )
                    )
                else:
                    lines.append("无。")
                lines.append("")

        if data["repeated_items"]:
            lines.extend(["### 重复元素（前 20）", ""])
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
            samples = data["samples"][sample_kind]
            if samples:
                lines.extend(
                    _md_table(
                        _sample_rows(samples),
                        ["record_id", "作品", "词头", "正文命中", "长度", "文本摘录"],
                    )
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

    annotations = profile["categories"]["annotations"]
    print(
        f"作品 {profile['record_count']}；"
        f"annotations {annotations['item_count']}；"
        f"commentaries {profile['categories']['commentaries']['item_count']}；"
        f"词头候选 {annotations['structure_candidates']['headword_candidates']['count']}；"
        f"结构异常 {profile['anomaly_count']}"
    )
    print(f"JSON：{args.json_output}")
    print(f"Markdown：{args.md_output}")
    print("注意：报告包含少量私人出版物派生文本，不要提交公开仓库。")


if __name__ == "__main__":
    main()
