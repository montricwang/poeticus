"""Profile the normalized Werneror/Poetry Work corpus before chunking.

Run after werneror_import:

    python -m scripts.corpus.werneror_profile

This is still corpus inspection only. It does not create chunks, embeddings,
vector indexes, or database tables.
"""
from __future__ import annotations

import argparse
import hashlib
import heapq
import json
import re
from collections import Counter
from pathlib import Path

DEFAULT_INPUT = Path("data/output/retrieval/werneror_works.jsonl")
DEFAULT_JSON_REPORT = Path("data/reports/werneror_corpus_profile.json")
DEFAULT_MD_REPORT = Path("data/reports/werneror_corpus_profile.md")

CLAUSE_SPLIT = re.compile(r"[，。！？；!?;]+")
SENTENCE_SPLIT = re.compile(r"[。！？!?]+")

DEFAULT_PROBES = {
    "杜甫《小寒食舟中作》": "片片轻鸥下急湍",
    "王维《送元二使安西》": "客舍青青柳色新",
    "韦庄《菩萨蛮》": "春水碧于天，画船听雨眠",
    "范仲淹《御街行》": "眉间心上，无计相回避",
    "杜牧《赠别》": "春风十里扬州路",
}


def _percentile(values: list[int], p: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[round((len(ordered) - 1) * p)]


def _chunk_count(text: str, pattern: re.Pattern[str]) -> int:
    return sum(1 for part in pattern.split(text) if part.strip())


def _digest(work: dict) -> bytes:
    payload = "\0".join(
        str(work.get(field, ""))
        for field in ("title", "dynasty", "author", "content")
    )
    return hashlib.sha256(payload.encode("utf-8")).digest()


def _short(text: str, limit: int = 120) -> str:
    text = text.replace("\r", " ").replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _label(work: dict) -> dict:
    return {
        "source_record_id": work["source_record_id"],
        "dynasty": work["dynasty"],
        "author": work["author"],
        "title": work["title"],
        "excerpt": _short(work["content"]),
    }


def _iter_jsonl(path: Path):
    with path.open(encoding="utf-8") as stream:
        for line_no, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                work = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"JSONL 第 {line_no} 行无法解析") from exc
            required = {
                "work_id", "title", "dynasty", "author", "content",
                "source", "source_record_id",
            }
            if not isinstance(work, dict) or not required <= set(work):
                raise ValueError(f"JSONL 第 {line_no} 行缺少 Work 字段")
            yield work


def profile_corpus(path: Path, probes: dict[str, str] | None = None) -> dict:
    if not path.is_file():
        raise ValueError(f"Work JSONL 不存在：{path}")
    probes = probes or DEFAULT_PROBES

    lengths = []
    by_dynasty = Counter()
    authors_by_dynasty: dict[str, set[str]] = {}
    all_authors = set()
    works_with_newline = 0

    question_total = 0
    question_distribution = Counter()
    question_works = []

    clause_chunks = 0
    sentence_chunks = 0

    seen_digests = set()
    duplicate_digests = set()
    duplicate_records = 0

    longest = []
    probe_hits = {name: [] for name in probes}
    records = 0

    for work in _iter_jsonl(path):
        records += 1
        content = work["content"]
        if not isinstance(content, str):
            raise ValueError(f"{work['source_record_id']}: content 不是字符串")

        length = len(content)
        lengths.append(length)
        by_dynasty[work["dynasty"]] += 1
        all_authors.add(work["author"])
        authors_by_dynasty.setdefault(work["dynasty"], set()).add(work["author"])

        if "\n" in content or "\r" in content:
            works_with_newline += 1

        q_count = content.count("?")
        if q_count:
            question_total += q_count
            question_distribution["5+" if q_count >= 5 else str(q_count)] += 1
            heapq.heappush(question_works, (q_count, records, _label(work)))
            if len(question_works) > 15:
                heapq.heappop(question_works)

        clause_chunks += _chunk_count(content, CLAUSE_SPLIT)
        sentence_chunks += _chunk_count(content, SENTENCE_SPLIT)

        digest = _digest(work)
        if digest in seen_digests:
            duplicate_records += 1
            duplicate_digests.add(digest)
        else:
            seen_digests.add(digest)

        heapq.heappush(longest, (length, records, _label(work)))
        if len(longest) > 15:
            heapq.heappop(longest)

        for name, phrase in probes.items():
            if phrase in content and len(probe_hits[name]) < 10:
                probe_hits[name].append(_label(work))

    duplicate_groups = {digest.hex(): [] for digest in duplicate_digests}
    if duplicate_digests:
        for work in _iter_jsonl(path):
            digest = _digest(work)
            if digest in duplicate_digests:
                group = duplicate_groups[digest.hex()]
                if len(group) < 10:
                    group.append(_label(work))

    return {
        "input": str(path),
        "records": records,
        "dynasties": len(by_dynasty),
        "authors": len(all_authors),
        "by_dynasty": dict(by_dynasty),
        "authors_by_dynasty": {
            dynasty: len(authors)
            for dynasty, authors in authors_by_dynasty.items()
        },
        "content_length_chars": {
            "min": min(lengths, default=0),
            "median": _percentile(lengths, 0.50),
            "p90": _percentile(lengths, 0.90),
            "p99": _percentile(lengths, 0.99),
            "max": max(lengths, default=0),
        },
        "works_with_newline": works_with_newline,
        "estimated_chunks": {
            "clause": clause_chunks,
            "sentence": sentence_chunks,
            "clause_per_work": round(clause_chunks / records, 3) if records else 0,
            "sentence_per_work": round(sentence_chunks / records, 3) if records else 0,
        },
        "question_marks": {
            "works": sum(question_distribution.values()),
            "characters": question_total,
            "works_by_count": dict(question_distribution),
            "top_examples": [
                {"question_marks": count, **label}
                for count, _, label in sorted(question_works, reverse=True)
            ],
        },
        "exact_duplicates": {
            "duplicate_records": duplicate_records,
            "groups": len(duplicate_groups),
            "examples": list(duplicate_groups.values())[:15],
        },
        "longest_works": [
            {"chars": length, **label}
            for length, _, label in sorted(longest, reverse=True)
        ],
        "coverage_probes": {
            name: {
                "phrase": probes[name],
                "found": bool(hits),
                "hits": hits,
            }
            for name, hits in probe_hits.items()
        },
    }


def _markdown(report: dict) -> str:
    length = report["content_length_chars"]
    chunks = report["estimated_chunks"]
    q = report["question_marks"]
    dup = report["exact_duplicates"]
    lines = [
        "# Werneror/Poetry Corpus Profile",
        "",
        f"- 作品：{report['records']:,}",
        f"- 朝代标签：{report['dynasties']}",
        f"- 作者：{report['authors']:,}",
        f"- 含换行作品：{report['works_with_newline']:,}",
        "",
        "## 正文长度",
        "",
        "| min | median | p90 | p99 | max |",
        "| ---: | ---: | ---: | ---: | ---: |",
        f"| {length['min']} | {length['median']} | {length['p90']} | {length['p99']} | {length['max']} |",
        "",
        "## 潜在 Chunk 规模",
        "",
        "| 切法 | Chunk 数 | 每首平均 |",
        "| --- | ---: | ---: |",
        f"| 分句（，。！？；） | {chunks['clause']:,} | {chunks['clause_per_work']} |",
        f"| 句号级（。！？） | {chunks['sentence']:,} | {chunks['sentence_per_work']} |",
        "",
        "## 问号替代字符",
        "",
        f"- 含问号作品：{q['works']:,}",
        f"- 问号总数：{q['characters']:,}",
        f"- 每首分布：{json.dumps(q['works_by_count'], ensure_ascii=False)}",
        "",
        "## 完全重复",
        "",
        f"- 重复记录：{dup['duplicate_records']}",
        f"- 重复组：{dup['groups']}",
        "",
        "## Ground Truth 覆盖探针",
        "",
        "| 来源 | 探针 | 是否找到 | 命中数（最多记录 10） |",
        "| --- | --- | --- | ---: |",
    ]
    for name, item in report["coverage_probes"].items():
        lines.append(
            f"| {name} | {item['phrase']} | {'是' if item['found'] else '否'} | {len(item['hits'])} |"
        )

    lines.extend(["", "## 最长作品样本", ""])
    for item in report["longest_works"][:10]:
        lines.append(
            f"- {item['chars']} 字｜{item['dynasty']}｜{item['author']}｜"
            f"{item['title']}｜{item['source_record_id']}｜{item['excerpt']}"
        )

    lines.extend(["", "## 问号最密集样本", ""])
    for item in q["top_examples"][:10]:
        lines.append(
            f"- {item['question_marks']} 个｜{item['dynasty']}｜{item['author']}｜"
            f"{item['title']}｜{item['source_record_id']}｜{item['excerpt']}"
        )

    lines.extend(["", "## 完全重复样本", ""])
    for group in dup["examples"][:10]:
        refs = "；".join(
            f"{item['source_record_id']} {item['dynasty']} {item['author']}《{item['title']}》"
            for item in group
        )
        lines.append(f"- {refs}")

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="画像 Werneror Work Corpus，供 Chunking / Retrieval 决策使用"
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--json-report", type=Path, default=DEFAULT_JSON_REPORT)
    parser.add_argument("--md-report", type=Path, default=DEFAULT_MD_REPORT)
    args = parser.parse_args()

    report = profile_corpus(args.input)
    args.json_report.parent.mkdir(parents=True, exist_ok=True)
    args.md_report.parent.mkdir(parents=True, exist_ok=True)
    args.json_report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.md_report.write_text(_markdown(report), encoding="utf-8")

    summary = {
        "records": report["records"],
        "authors": report["authors"],
        "content_length_chars": report["content_length_chars"],
        "estimated_chunks": report["estimated_chunks"],
        "question_marks": {
            key: report["question_marks"][key]
            for key in ("works", "characters", "works_by_count")
        },
        "exact_duplicates": {
            key: report["exact_duplicates"][key]
            for key in ("duplicate_records", "groups")
        },
        "coverage_probes": {
            name: item["found"]
            for name, item in report["coverage_probes"].items()
        },
        "json_report": str(args.json_report),
        "md_report": str(args.md_report),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
