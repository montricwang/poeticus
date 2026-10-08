"""Probe targeted CNKGraph reference queries."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from backend.data_paths import EVAL_REPORTS_ROOT

import httpx

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = EVAL_REPORTS_ROOT / "cnkgraph_reference_targets_10061645.json"
BASE_URL = os.getenv("CNKGRAPH_BASE_URL", "https://api.cnkgraph.com").rstrip("/")

CASES = [
    ("near_quote_lu_you", "片片轻鸥落晚沙", "杜甫《小寒食舟中作》：片片轻鸥下急湍"),
    ("adapted_quote_zhou_1", "客舍青青", "王维《渭城曲》：客舍青青柳色新"),
    ("adapted_quote_zhou_2", "渭城荒远无交旧", "王维《渭城曲》送别语境"),
    ("adapted_quote_li", "才下眉头，却上心头", "范仲淹《御街行》：眉间心上，无计相回避"),
    ("compressed_cue_su", "未满三朝已食牛", "《尸子》/类书：虎豹之驹，有食牛之气"),
    ("transformed_yan", "一弦弹尽仙韶乐", "《淮南子》：一弦不足以见悲"),
    ("later_parallel_jiang", "三十六陂秋色", "观察姜夔之前的“三十六陂”来源"),
]


def refs_from(raw):
    rows = []
    sentences = raw.get("Sentences", []) if isinstance(raw, dict) else []
    for sentence in sentences if isinstance(sentences, list) else []:
        if not isinstance(sentence, dict):
            continue
        refs = sentence.get("References", [])
        for ref in refs if isinstance(refs, list) else []:
            if not isinstance(ref, dict):
                continue
            rows.append({
                "query_clause": sentence.get("Clause"),
                "reference_clause": ref.get("Clause"),
                "dynasty": ref.get("Dynasty"),
                "author": ref.get("Author"),
                "title": ref.get("Title"),
                "writing_id": ref.get("WritingId"),
            })
    return rows


async def main_async():
    results = []
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=20.0) as client:
        for case_id, content, expected_hint in CASES:
            response = await client.post(
                "/api/tool/reference",
                json={"content": content},
            )
            response.raise_for_status()
            refs = refs_from(response.json())
            results.append({
                "id": case_id,
                "content": content,
                "expected_hint": expected_hint,
                "status": "ok" if refs else "no_hit",
                "reference_count": len(refs),
                "references": refs[:30],
            })
    return {
        "probe_id": "cnkgraph_reference_targets_10061645",
        "endpoint": "/api/tool/reference",
        "results": results,
    }


def main():
    result = asyncio.run(main_async())
    for row in result["results"]:
        print(f"\n[{row['id']}] {row['status']} ({row['reference_count']})")
        for index, ref in enumerate(row["references"][:10], start=1):
            source = " ".join(
                str(value) for value in (
                    ref.get("dynasty"),
                    ref.get("author"),
                    ref.get("title"),
                ) if value
            )
            print(f"  {index:>2}. {source}: {ref.get('reference_clause') or ''}")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"\n已保存：{OUTPUT}")


if __name__ == "__main__":
    main()
