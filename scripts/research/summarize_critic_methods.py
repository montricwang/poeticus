"""Summarize private critic-method records without exporting literary text."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
from itertools import combinations
import json
from pathlib import Path
from typing import Any


def summarize(path: Path, expected_count: int | None = None) -> dict[str, Any]:
    essays = 0
    methods_total = 0
    method_entries: Counter[str] = Counter()
    method_essays: Counter[str] = Counter()
    critics: Counter[str] = Counter()
    critic_methods: dict[str, Counter[str]] = defaultdict(Counter)
    method_pairs: Counter[tuple[str, str]] = Counter()
    schemas: Counter[str] = Counter()
    essay_numbers: set[int] = set()
    digest = hashlib.sha256()

    with path.open("rb") as source:
        for line_number, raw_line in enumerate(source, start=1):
            digest.update(raw_line)
            if not raw_line.strip():
                continue
            row = json.loads(raw_line)
            number = row.get("essay_no")
            if not isinstance(number, int) or number in essay_numbers:
                raise ValueError(f"Invalid or duplicate essay_no at line {line_number}")
            essay_numbers.add(number)
            methods = row.get("methods")
            if not isinstance(methods, list):
                raise ValueError(f"Missing methods list at line {line_number}")
            codes = []
            for method in methods:
                code = method.get("code") if isinstance(method, dict) else None
                if not isinstance(code, str) or not code.strip():
                    raise ValueError(f"Invalid method code at line {line_number}")
                codes.append(code.strip())
            critic = row.get("critic") or ""
            if not isinstance(critic, str):
                raise ValueError(f"Invalid critic signature at line {line_number}")
            critic = critic.strip()

            essays += 1
            methods_total += len(codes)
            method_entries.update(codes)
            unique_codes = sorted(set(codes))
            method_essays.update(unique_codes)
            critics[critic] += 1
            critic_methods[critic].update(unique_codes)
            method_pairs.update(combinations(unique_codes, 2))
            schemas[row.get("_origin_schema", "unknown")] += 1

    if not essays or (expected_count is not None and essays != expected_count):
        raise ValueError(f"Expected {expected_count} essays; found {essays}")

    def ranked(counter: Counter[Any]) -> list[tuple[Any, int]]:
        return sorted(counter.items(), key=lambda item: (-item[1], item[0]))

    return {
        "source": path.name,
        "sha256": digest.hexdigest(),
        "essays": essays,
        "methods_total": methods_total,
        "methods_per_essay": round(methods_total / essays, 2),
        "critics": len(critics) - int("" in critics),
        "unknown_critic_essays": critics[""],
        "single_essay_critics": sum(count == 1 for critic, count in critics.items() if critic),
        "critics_with_ten_essays": sum(count >= 10 for critic, count in critics.items() if critic),
        "schemas": dict(schemas),
        "method_entries": ranked(method_entries),
        "method_essays": ranked(method_essays),
        "critic_essays": ranked(critics),
        "critic_method_essays": {critic: dict(counter) for critic, counter in critic_methods.items()},
        "method_pairs": [(first, second, count) for (first, second), count in ranked(method_pairs)],
    }


def render_markdown(data: dict[str, Any]) -> str:
    n = data["essays"]
    entries = dict(data["method_entries"])
    presence = dict(data["method_essays"])
    lines = [
        "# 《唐宋词鉴赏辞典》1505 篇批评方法统计概览",
        "",
        f"数据：`{data['source']}`；SHA-256：`{data['sha256']}`。",
        "",
        f"共 {n} 篇、{data['methods_total']} 条方法分析（平均 {data['methods_per_essay']} 条/篇）、"
        f"{len(entries)} 种方法标签、{data['critics']} 种评论者署名字符串。",
        "",
        "## 方法分布",
        "",
        "| 方法标签 | 涉及篇数 | 占 1505 篇比例 | 方法条数 |",
        "| --- | ---: | ---: | ---: |",
    ]
    for code, count in data["method_essays"]:
        lines.append(f"| `{code}` | {count} | {count / n:.1%} | {entries[code]} |")
    lines += [
        "",
        "同一篇可以使用多个标签；涉及篇数对同篇同标签去重，方法条数不去重，比例不能相加。",
        "",
        "## 评论者分布",
        "",
        f"{data['critics_with_ten_essays']} 种署名至少出现 10 篇，"
        f"{data['single_essay_critics']} 种署名只出现 1 篇；"
        f"无署名 {data['unknown_critic_essays']} 篇。",
        "",
        "| 评论者署名 | 篇数 | 最常见的 3 类方法（涉及篇数） |",
        "| --- | ---: | --- |",
    ]
    for critic, count in data["critic_essays"][:20]:
        profile = sorted(data["critic_method_essays"][critic].items(), key=lambda v: (-v[1], v[0]))
        shown = "、".join(f"`{code}` {freq}" for code, freq in profile[:3])
        lines.append(f"| {critic or '（无署名）'} | {count} | {shown} |")
    lines += [
        "",
        "评论者按原始署名字符串统计，未消歧或合并异写；标签差异不能直接归因于个人风格，"
        "因为评论者的篇目、作品、数量不同。",
        "",
        "## 方法组合",
        "",
        "| 两种标签 | 同时出现的篇数 | 占全部篇目 | 相对独立基线倍数 |",
        "| --- | ---: | ---: | ---: |",
    ]
    for first, second, count in data["method_pairs"][:15]:
        lift = n * count / (presence[first] * presence[second])
        lines.append(f"| `{first}` + `{second}` | {count} | {count / n:.1%} | {lift:.2f} |")
    lines += [
        "",
        "组合按篇统计，同篇中两种标签各出现至少一次即记一次。"
        "「相对独立基线倍数」= 实际共同出现篇数 ÷（两标签各自出现篇数之积 / 总篇数）；"
        "约为 1 时，共现主要由各自的高频率解释，不能当作特殊关联。",
        "",
        "## 使用边界",
        "",
        "- 这是现有 AI 初标及六篇复查后的**描述性统计**，没有测量全库分类准确率。",
        "- 数量不能表示方法的文学价值，也不能证明某评论者拥有独特方法。",
        "- 下一步应据此挑选有代表性的原始赏析，核对分析过程，再尝试提炼可迁移的方法。",
        "- 统计仅输出方法代码、篇数及评论者署名；不输出书籍正文、现代赏析或研究卡原文。",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--expected-count", type=int)
    parser.add_argument("--output", type=Path, help="Write a new Markdown report; refuse overwrite")
    args = parser.parse_args()
    result = render_markdown(summarize(args.input, args.expected_count))
    if args.output:
        with args.output.open("x", encoding="utf-8") as output:
            output.write(result)
    else:
        print(result)


if __name__ == "__main__":
    main()
