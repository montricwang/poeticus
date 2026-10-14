"""只读补漏：检查未识别长 Work 是否包含两首以上独立诗篇（不要求全文覆盖）。

仅出候选报告，不作为可自动过滤的关系证据。面向标题有多首/组诗信号的
Work；正文按 NFKC、忽略标点空白对齐。用于发现插入题序或不完整拼接。
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from backend.data_paths import RETRIEVAL_CORPUS_ROOT, RETRIEVAL_REPORTS_ROOT
from scripts.corpus.scan_normalized_compositions import PREFIX, normalize_poem

NUM = "一二三四五六七八九十百千万零〇廿卅两0123456789"
GROUP_NUMBER = re.compile("[" + NUM + "]+(?:首|篇|阕|闋|曲|绝|絕|律|咏|詠|章|则|則|拍|题|題)")
MEMBER_NUMBER = re.compile("其[" + NUM + "]+|之[" + NUM + "]+(?=\\s|$)")
SOURCE = RETRIEVAL_CORPUS_ROOT / "werneror_works.jsonl"
REPORT = RETRIEVAL_REPORTS_ROOT / "werneror_partial_compositions_review.json"


def main() -> None:
    known = set()
    for file in (
        RETRIEVAL_REPORTS_ROOT / "werneror_group_audit_matches.jsonl",
        RETRIEVAL_REPORTS_ROOT / "werneror_group_normalized_matches.jsonl",
    ):
        for line in file.open(encoding="utf-8"):
            known.add(json.loads(line)["work_id"])
    entries = {}
    starts = defaultdict(list)
    for line in SOURCE.open(encoding="utf-8"):
        w = json.loads(line)
        norm = normalize_poem(w["content"])
        entry = (w["author"], w["dynasty"], w["title"], norm)
        entries[w["work_id"]] = entry
        if len(norm) >= 24 and w["author"]:
            starts[(w["author"], w["dynasty"], norm[:PREFIX])].append(w["work_id"])

    result = []
    totals = Counter()
    for host_id, (author, dynasty, title, text) in entries.items():
        if host_id in known or len(text) < 48 or not author:
            continue
        totals["unchecked_hosts"] += 1
        # 分组提示既可能出现于父标题，也可能仅出现在成员标题。
        has_parent_signal = bool(GROUP_NUMBER.search(title) or "组诗" in title)
        matches = []
        pos = 0
        while pos + 24 <= len(text):
            best = None
            for member_id in starts.get((author, dynasty, text[pos:pos + PREFIX]), ()):
                if member_id == host_id:
                    continue
                _, _, child_title, child = entries[member_id]
                if len(child) >= len(text) or not text.startswith(child, pos):
                    continue
                if not (has_parent_signal or MEMBER_NUMBER.search(child_title)):
                    continue
                if best is None or len(child) > len(best[1]):
                    best = (member_id, child)
            if best is None:
                pos += 1
                continue
            matches.append((pos, pos + len(best[1]), best[0]))
            pos += len(best[1])

        if len(matches) < 2:
            continue
        covered = sum(end-start for start,end,_ in matches)
        fraction = covered/len(text)
        totals["hosts_with_two_or_more_members"] += 1
        if fraction >= .8:totals["covered_at_least_80pct"] += 1
        if fraction >= .95:totals["covered_at_least_95pct"] += 1
        if fraction < .8:continue
        # 仅供人工核对，不直接加关系。
        result.append({
            "parent_work_id": host_id, "title": title, "author": author,
            "parts": len(matches), "coverage": round(fraction, 4),
            "matched_parts": [{
                "work_id": mid, "title": entries[mid][2], "begin": begin, "end": end,
            } for begin,end,mid in matches],
        })
    report = {"counts": dict(totals), "matches": result}
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf8")
    print(json.dumps({
        "counts":dict(totals), "report":str(REPORT),
        "examples":[{"title":x["title"],"author":x["author"],"parts":x["parts"],"coverage":x["coverage"]} for x in result[:25]],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
