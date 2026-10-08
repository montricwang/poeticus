"""一次性探针：复用 qingshang 使用过的 CNKGraph /api/tool/reference，
检查它对“前代成句 / 化用 / 高度变形”问题的覆盖。

本脚本只做诊断，不进入 Poeticus 正式运行路径。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

from backend.data_paths import EVAL_REPORTS_ROOT
from typing import Any

import httpx


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = EVAL_REPORTS_ROOT / "cnkgraph_reference_probe_10061630.json"
BASE_URL = os.getenv("CNKGRAPH_BASE_URL", "https://api.cnkgraph.com").rstrip("/")

DEFAULT_CASES = [
    {
        "id": "near_quote_lu_you",
        "content": "双双新燕飞春岸，片片轻鸥落晚沙。",
        "expected_hint": "杜甫《小寒食舟中作》：片片轻鸥下急湍",
    },
    {
        "id": "adapted_quote_zhou_bangyan",
        "content": "雨过朦胧斜日透，客舍青青，特地添明秀。莫话扬鞭回别首，渭城荒远无交旧。",
        "expected_hint": "王维《送元二使安西》：渭城朝雨、客舍青青",
    },
    {
        "id": "compressed_cue_su_shi",
        "content": "壮气横秋，未满三朝已食牛。",
        "expected_hint": "《尸子》/类书所引：虎豹之驹，未成文，而有食牛之气",
    },
    {
        "id": "transformed_use_yan_jidao",
        "content": "一弦弹尽《仙韶》乐，曾破千金学。",
        "expected_hint": "《淮南子》：一弦不足以见悲；属于反用/翻转",
    },
    {
        "id": "adapted_quote_li_qingzhao",
        "content": "此情无计可消除，才下眉头，却上心头。",
        "expected_hint": "范仲淹《御街行》：眉间心上，无计相回避",
    },
    {
        "id": "later_parallel_jiang_kui",
        "content": "问甚时同赋，三十六陂秋色。",
        "expected_hint": "应优先返回姜夔之前的来源；王沂孙属于后世平行文本",
    },
]


def _as_items(raw: Any, key: str | None = None) -> list[dict[str, Any]]:
    if key and isinstance(raw, dict):
        raw = raw.get(key)
    if isinstance(raw, dict):
        return [raw] if raw else []
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    return []


def _flatten_reference(raw: Any) -> list[dict[str, Any]]:
    rows = []
    for sentence in _as_items(raw, "Sentences"):
        clause = sentence.get("Clause")
        for ref in _as_items(sentence.get("References")):
            rows.append(
                {
                    "query_clause": clause,
                    "reference_clause": ref.get("Clause"),
                    "dynasty": ref.get("Dynasty"),
                    "author": ref.get("Author"),
                    "title": ref.get("Title"),
                    "raw": ref,
                }
            )
    return rows


async def _probe_one(
    client: httpx.AsyncClient,
    case: dict[str, str],
) -> dict[str, Any]:
    try:
        response = await client.post(
            "/api/tool/reference",
            json={"content": case["content"]},
        )
        response.raise_for_status()
        raw = response.json()
        refs = _flatten_reference(raw)
        return {
            **case,
            "status": "ok" if refs else "no_hit",
            "reference_count": len(refs),
            "references": refs[:10],
        }
    except httpx.HTTPStatusError as exc:
        return {
            **case,
            "status": "error",
            "reference_count": 0,
            "error": f"HTTP {exc.response.status_code}",
            "references": [],
        }
    except (httpx.RequestError, ValueError) as exc:
        return {
            **case,
            "status": "error",
            "reference_count": 0,
            "error": str(exc),
            "references": [],
        }


async def run_probe(cases: list[dict[str, str]]) -> dict[str, Any]:
    async with httpx.AsyncClient(
        base_url=BASE_URL,
        timeout=20.0,
    ) as client:
        results = []
        for case in cases:
            results.append(await _probe_one(client, case))
    return {
        "probe_id": "cnkgraph_reference_10061630",
        "endpoint": "/api/tool/reference",
        "results": results,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = asyncio.run(run_probe(DEFAULT_CASES))

    for row in result["results"]:
        print(
            f"\n[{row['id']}] {row['status']} "
            f"(references={row['reference_count']})"
        )
        print(f"输入：{row['content']}")
        print(f"预期线索：{row['expected_hint']}")
        for ref in row["references"][:5]:
            source = " ".join(
                str(x)
                for x in (
                    ref.get("dynasty"),
                    ref.get("author"),
                    ref.get("title"),
                )
                if x
            )
            print(
                f"  - {source or '未知来源'}: "
                f"{ref.get('reference_clause') or ''}"
            )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"\n已保存：{args.output}")


if __name__ == "__main__":
    main()
