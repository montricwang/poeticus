"""只读第二轮扫描：发现 Werneror 作品格式差异造成的漏检合集。

候选必须由同作者同朝代至少两条完整 Work 的归一化正文顺序拼接而成。
不进行语义匹配或模糊字词编辑，保证自动过滤的证据可复算。

生成新审计明细后，再由 export_work_compositions 逐条重验。
"""
from __future__ import annotations

import argparse
import heapq
import json
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from backend.data_paths import RETRIEVAL_CORPUS_ROOT, RETRIEVAL_REPORTS_ROOT

DEFAULT_WORKS = RETRIEVAL_CORPUS_ROOT / "werneror_works.jsonl"
DEFAULT_EXACT = RETRIEVAL_REPORTS_ROOT / "werneror_group_audit_matches.jsonl"
DEFAULT_EXTRA = RETRIEVAL_REPORTS_ROOT / "werneror_group_normalized_matches.jsonl"
DEFAULT_SUMMARY = RETRIEVAL_REPORTS_ROOT / "werneror_group_normalized_summary.json"
PREFIX = 12


def normalize_poem(text: str) -> str:
    """消除仅涉及排版、标点、全半角的差异；保留全部有效汉字。"""
    return "".join(
        character for original in text
        for character in unicodedata.normalize("NFKC", original)
        if character.isalnum()
    )


def _find_pieces(
    host_id: str,
    author: str,
    dynasty: str,
    text: str,
    entries: dict[str, dict[str, str]],
    starts: dict[tuple[str, str, str], list[str]],
    *,
    min_length: int,
) -> list[str] | None:
    if len(text) < 2 * min_length or not author:
        return None
    parents: dict[int, tuple[int, str] | None] = {0: None}
    pending = [0]
    while pending:
        pos = heapq.heappop(pending)
        if pos == len(text):
            break
        for member_id in starts.get((author, dynasty, text[pos:pos + PREFIX]), ()):
            if member_id == host_id:
                continue
            m = entries[member_id]["normalized"]
            if len(m) >= len(text) or not text.startswith(m, pos):
                continue
            end = pos + len(m)
            if end not in parents:
                parents[end] = (pos, member_id)
                heapq.heappush(pending, end)
    if len(text) not in parents:
        return None
    ids = []
    pos = len(text)
    while pos:
        parent = parents[pos]
        if parent is None:
            return None
        pos, member_id = parent
        ids.append(member_id)
    if len(ids) < 2:
        return None
    ids.reverse()
    return ids


def scan(
    works_path: Path,
    exact_path: Path,
    extra_path: Path,
    summary_path: Path,
    *,
    min_length: int = 24,
) -> dict[str, object]:
    already: set[str] = set()
    with exact_path.open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                already.add(json.loads(line)["work_id"])

    entries: dict[str, dict[str, str]] = {}
    starts: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    with works_path.open(encoding="utf-8") as stream:
        for line in stream:
            work = json.loads(line)
            work_id = work["work_id"]
            norm = normalize_poem(work["content"])
            entries[work_id] = {
                "normalized": norm,
                "content": work["content"],
                "author": work["author"],
                "dynasty": work["dynasty"],
                "title": work["title"],
                "source_record_id": work["source_record_id"],
            }
            if work["author"] and len(norm) >= min_length:
                starts[(work["author"], work["dynasty"], norm[:PREFIX])].append(work_id)

    counts: Counter[str] = Counter()
    examples: list[dict[str, object]] = []
    extra_path.parent.mkdir(parents=True, exist_ok=True)
    with extra_path.open("w", encoding="utf-8") as output:
        for parent_id, parent in entries.items():
            if parent_id in already:
                continue
            counts["examined_non_exact_hosts"] += 1
            members = _find_pieces(
                parent_id, parent["author"], parent["dynasty"],
                parent["normalized"], entries, starts, min_length=min_length,
            )
            if not members:
                continue
            if "".join(entries[m]["content"] for m in members) == parent["content"]:
                # 在原始审计中没有被接受，却是逐字相等：单列以供检查。
                counts["unexpected_exact"] += 1
                continue
            counts["new_normalized_aggregates"] += 1
            counts["new_member_links"] += len(members)
            if "其" in parent["title"] or any("其" in entries[m]["title"] for m in members):
                counts["title_has_qi"] += 1
            row = {
                "source_record_id": parent["source_record_id"],
                "work_id": parent_id,
                "title": parent["title"],
                "author": parent["author"],
                "dynasty": parent["dynasty"],
                "chars": len(parent["content"]),
                "parts": len(members),
                "member_source_record_ids": [entries[m]["source_record_id"] for m in members],
                "member_titles": [entries[m]["title"] for m in members],
                "member_dynasties": [entries[m]["dynasty"] for m in members],
                "match_kind": "normalized_concatenation",
            }
            output.write(json.dumps(row, ensure_ascii=False) + "\n")
            if len(examples) < 30:
                examples.append(row)

    summary: dict[str, object] = {
        "corpus_records": len(entries),
        "already_exact_aggregates": len(already),
        "min_normalized_member_chars": min_length,
        "counts": dict(counts),
        "examples": examples,
        "limitations": [
            "Only normalized full concatenations, not incomplete groups or semantic variants",
            "NFKC and punctuation normalization may erase meaningful symbols; review before admission",
        ],
    }
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--works", type=Path, default=DEFAULT_WORKS)
    parser.add_argument("--exact", type=Path, default=DEFAULT_EXACT)
    parser.add_argument("--extra", type=Path, default=DEFAULT_EXTRA)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    args = parser.parse_args()
    result = scan(args.works, args.exact, args.extra, args.summary)
    print(json.dumps(result["counts"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
