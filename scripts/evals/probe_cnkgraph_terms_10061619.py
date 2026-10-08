"""一次性探针：确认 CNKGraph 对几类典故/文本关系查询词的覆盖。

用于解释 2026-10-06 Intertext Eval 首轮结果，不进入正式运行路径。
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from backend.data_paths import EVAL_REPORTS_ROOT

from backend.evidence.providers.cnkgraph import CNKGraphProvider


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = EVAL_REPORTS_ROOT / "cnkgraph_probe_10061619.json"

DEFAULT_TERMS = [
    "食牛",
    "食牛之气",
    "虎豹之驹",
    "片片轻鸥",
    "片片轻鸥落晚沙",
    "刘伶",
]


async def probe(terms: list[str]) -> dict:
    provider = CNKGraphProvider()
    rows = []

    for term in terms:
        try:
            items = await provider.search(term, evidence_type="allusion")
            rows.append(
                {
                    "term": term,
                    "status": "ok" if items else "no_hit",
                    "count": len(items),
                    "items": [
                        {
                            "text": item.text[:500],
                            "source": (
                                item.source.model_dump()
                                if item.source is not None
                                else None
                            ),
                        }
                        for item in items[:3]
                    ],
                }
            )
        except Exception as exc:  # probe 要把失败也记录下来
            rows.append(
                {
                    "term": term,
                    "status": "error",
                    "count": 0,
                    "error": str(exc),
                    "items": [],
                }
            )

    return {"probe_id": "cnkgraph_terms_10061619", "results": rows}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("terms", nargs="*", help="可选：覆盖默认查询词")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    terms = args.terms or DEFAULT_TERMS
    result = asyncio.run(probe(terms))

    for row in result["results"]:
        print(
            f"{row['term']}: {row['status']} "
            f"(count={row['count']})"
        )
        for item in row["items"]:
            source = item.get("source") or {}
            title = source.get("title") or "无来源标题"
            preview = item["text"].replace("\n", " ")[:160]
            print(f"  - {title}: {preview}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"\n已保存：{args.output}")


if __name__ == "__main__":
    main()
