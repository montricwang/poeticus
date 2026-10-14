"""只读审计：找出 Werneror Work 被同作者其他完整 Work 顺序拼接的记录。

目标是生成可人工复核的候选清单，不修改原语料、索引或数据库。
例如：
    python -m scripts.corpus.werneror_group_audit
"""
from __future__ import annotations

import argparse
import heapq
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from backend.data_paths import RETRIEVAL_CORPUS_ROOT, RETRIEVAL_REPORTS_ROOT

DEFAULT_INPUT = RETRIEVAL_CORPUS_ROOT / "werneror_works.jsonl"
DEFAULT_REPORT = RETRIEVAL_REPORTS_ROOT / "werneror_group_audit.json"
DEFAULT_DETAILS = RETRIEVAL_REPORTS_ROOT / "werneror_group_audit_matches.jsonl"
PREFIX_LEN = 12


@dataclass(slots=True, frozen=True)
class Work:
    work_id: str
    source_record_id: str
    title: str
    author: str
    dynasty: str
    content: str


def _load_records(path: Path, min_piece: int) -> tuple[list[Work], dict[tuple[str, str], list[int]]]:
    works: list[Work] = []
    starts: dict[tuple[str, str], list[int]] = defaultdict(list)
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            row = json.loads(line)
            work = Work(
                work_id=row["work_id"],
                source_record_id=row["source_record_id"],
                title=row["title"],
                author=row["author"],
                dynasty=row["dynasty"],
                content=row["content"],
            )
            index = len(works)
            works.append(work)
            if work.author and len(work.content) >= min_piece:
                starts[(work.author, work.content[:PREFIX_LEN])].append(index)
    return works, starts


def find_exact_components(
    host: Work,
    works: list[Work],
    starts: dict[tuple[str, str], list[int]],
    *,
    min_piece: int = 24,
) -> list[Work] | None:
    """返回完全覆盖 host.content 的 2+ 个独立 Work；无证据则返回 None。

    最短成员长度控制极短套语的偶然拼接；匹配本身严格要求正文逐字相等。
    不要求各部分与 host 同源文件，因为重复往往跨文件。
    """
    text = host.content
    if len(text) < min_piece * 2 or not host.author:
        return None

    parents: dict[int, tuple[int, int] | None] = {0: None}
    queue = [0]
    while queue:
        pos = heapq.heappop(queue)
        if pos == len(text):
            break
        key = (host.author, text[pos:pos + PREFIX_LEN])
        for index in starts.get(key, ()):
            piece = works[index]
            if len(piece.content) >= len(text):  # 排除本身、以及等长的重复记录
                continue
            if not text.startswith(piece.content, pos):
                continue
            end = pos + len(piece.content)
            if end not in parents:
                parents[end] = (pos, index)
                heapq.heappush(queue, end)

    if len(text) not in parents:
        return None

    indices = []
    pos = len(text)
    while pos:
        parent = parents[pos]
        if parent is None:
            return None
        pos, index = parent
        indices.append(index)
    if len(indices) < 2:
        return None
    indices.reverse()
    return [works[i] for i in indices]


def audit(
    input_path: Path,
    report_path: Path,
    details_path: Path,
    *,
    min_piece: int = 24,
    max_works: int | None = None,
) -> dict[str, object]:
    works, starts = _load_records(input_path, min_piece)
    by_dynasty: Counter[str] = Counter()
    by_author: Counter[str] = Counter()
    by_source_file: Counter[str] = Counter()
    piece_counts: Counter[int] = Counter()
    cross_file_count = 0
    candidates = 0
    examples: list[dict[str, object]] = []
    report_path.parent.mkdir(parents=True, exist_ok=True)
    details_path.parent.mkdir(parents=True, exist_ok=True)

    with details_path.open("w", encoding="utf-8") as output:
        for host in works[:max_works] if max_works else works:
            members = find_exact_components(host, works, starts, min_piece=min_piece)
            if members is None:
                continue
            candidates += 1
            by_dynasty[host.dynasty] += 1
            by_author[host.author] += 1
            by_source_file[host.source_record_id.rsplit(":", 1)[0]] += 1
            piece_counts[len(members)] += 1
            cross_file_count += any(
                piece.source_record_id.rsplit(":", 1)[0]
                != host.source_record_id.rsplit(":", 1)[0]
                for piece in members
            )
            row = {
                "source_record_id": host.source_record_id,
                "work_id": host.work_id,
                "title": host.title,
                "author": host.author,
                "dynasty": host.dynasty,
                "chars": len(host.content),
                "parts": len(members),
                "member_source_record_ids": [m.source_record_id for m in members],
                "member_titles": [m.title for m in members],
                "member_dynasties": [m.dynasty for m in members],
            }
            output.write(json.dumps(row, ensure_ascii=False) + "\n")
            if len(examples) < 24:
                examples.append(row)

    result: dict[str, object] = {
        "method": "exact full concatenation of >=2 shorter works of the same author",
        "min_member_chars": min_piece,
        "total_works": len(works),
        "scanned_hosts": min(len(works), max_works) if max_works else len(works),
        "candidate_aggregates": candidates,
        "cross_source_file_candidates": cross_file_count,
        "by_dynasty": dict(by_dynasty.most_common()),
        "by_author_top_30": dict(by_author.most_common(30)),
        "by_source_file_top_30": dict(by_source_file.most_common(30)),
        "parts_distribution": dict(sorted(piece_counts.items())),
        "examples": examples,
        "details_path": str(details_path),
        "limitations": [
            "Counts are strict lower bounds; variants, punctuation differences and missing standalone parts are missed.",
            "Exact concatenation is not a license to delete an original literary collection or group title.",
            "The dataset is imported JSONL; the upstream CSV was unavailable in the WSL workspace.",
        ],
    }
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--details", type=Path, default=DEFAULT_DETAILS)
    parser.add_argument("--min-piece", type=int, default=24)
    parser.add_argument("--max-works", type=int)
    args = parser.parse_args()
    if args.min_piece < PREFIX_LEN:
        parser.error(f"--min-piece 不可小于 {PREFIX_LEN}")
    report = audit(
        args.input, args.report, args.details,
        min_piece=args.min_piece, max_works=args.max_works,
    )
    print(json.dumps({k: v for k, v in report.items() if k != "examples"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
