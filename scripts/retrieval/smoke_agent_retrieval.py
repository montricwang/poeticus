"""Run real Agent -> HTTP Retrieval Service -> Agent smoke cases.

Prerequisites:

1. Start the local Retrieval Service in another terminal:
       python -m scripts.retrieval.run_serving
2. Keep a valid LLM_API_KEY in .env.

This script uses the real Agent and real Retrieval Service. It resolves the
benchmark current poem to a full Corpus Work before invoking the Agent so the
normal exact-content self-hit path is exercised.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CASES = ROOT / "evals/retrieval_increment_cases.json"
DEFAULT_REPORT_ROOT = ROOT / "data/reports"
DEFAULT_CASE_IDS = (
    "longtail_luyou_dufu_gull",
    "compressed_jiangkui_dumu_qinglou",
)
DEFAULT_METADATA_MANIFEST = Path(
    "../poeticus-data/output/retrieval/"
    "serving/retrieval_metadata.manifest.json"
)


def load_cases(path: Path, case_ids: tuple[str, ...]) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    by_id = {item["id"]: item for item in payload["cases"]}
    missing = [case_id for case_id in case_ids if case_id not in by_id]
    if missing:
        raise ValueError(
            "Smoke case 不存在：" + ", ".join(missing)
        )
    return [by_id[case_id] for case_id in case_ids]


def resolve_full_current_works(
    work_path: Path,
    cases: list[dict],
) -> dict[str, dict]:
    """Find one full current Work per case by author + known current text."""
    unresolved = {case["id"] for case in cases}
    resolved: dict[str, dict] = {}

    with work_path.open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            work = json.loads(line)
            content = work.get("content")
            if not isinstance(content, str):
                continue

            for case in cases:
                case_id = case["id"]
                if case_id not in unresolved:
                    continue
                if work.get("author") != case["input"]["context"].get(
                    "author"
                ):
                    continue
                if case["current_match_text"] not in content:
                    continue
                resolved[case_id] = work
                unresolved.remove(case_id)

            if not unresolved:
                break

    if unresolved:
        raise ValueError(
            "无法从 Corpus 解析当前完整作品："
            + ", ".join(sorted(unresolved))
        )
    return resolved


def parse_tool_events(tool_results: list[dict]) -> list[dict]:
    events = []
    for item in tool_results:
        content = item.get("content")
        if not isinstance(content, str):
            continue
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            payload = {"status": "invalid_json", "raw": content[:500]}

        candidates = payload.get("candidates")
        preview = []
        if isinstance(candidates, list):
            preview = [
                {
                    "rank": candidate.get("rank"),
                    "author": candidate.get("author"),
                    "title": candidate.get("title"),
                    "text": candidate.get("text"),
                }
                for candidate in candidates[:8]
                if isinstance(candidate, dict)
            ]

        events.append(
            {
                "tool_call_id": item.get("id"),
                "status": payload.get("status"),
                "evidence_type": payload.get("evidence_type"),
                "query": payload.get("query"),
                "candidates": preview,
            }
        )
    return events


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="真实 Agent -> Retrieval Service 端到端 smoke"
    )
    parser.add_argument(
        "--retrieval-url",
        default="http://127.0.0.1:8787",
    )
    parser.add_argument(
        "--api-token",
        default=os.getenv("POETICUS_TEXT_RETRIEVAL_TOKEN", ""),
    )
    parser.add_argument(
        "--metadata-manifest",
        type=Path,
        default=DEFAULT_METADATA_MANIFEST,
    )
    parser.add_argument(
        "--cases",
        type=Path,
        default=DEFAULT_CASES,
    )
    parser.add_argument(
        "--case",
        action="append",
        dest="case_ids",
    )
    parser.add_argument("--output-prefix", type=Path)
    args = parser.parse_args()

    if not os.getenv("LLM_API_KEY"):
        raise SystemExit("缺少 LLM_API_KEY；请检查本地 .env")

    retrieval_url = args.retrieval_url.rstrip("/")
    headers = {}
    if args.api_token:
        headers["Authorization"] = f"Bearer {args.api_token}"

    try:
        response = httpx.get(
            retrieval_url + "/health",
            timeout=5.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise SystemExit(
            "Retrieval Service 不可用；请先在另一个终端运行 "
            "python -m scripts.retrieval.run_serving"
        ) from exc

    # The Agent client reads these during module import.
    os.environ["POETICUS_TEXT_RETRIEVAL_URL"] = retrieval_url
    if args.api_token:
        os.environ["POETICUS_TEXT_RETRIEVAL_TOKEN"] = args.api_token

    metadata_manifest = args.metadata_manifest.expanduser().resolve()
    if not metadata_manifest.is_file():
        raise SystemExit(
            f"metadata manifest 不存在：{metadata_manifest}"
        )
    metadata = json.loads(
        metadata_manifest.read_text(encoding="utf-8")
    )
    work_path = Path(metadata["work_path"])

    case_ids = tuple(args.case_ids or DEFAULT_CASE_IDS)
    cases = load_cases(args.cases, case_ids)
    current_works = resolve_full_current_works(work_path, cases)

    # Import only after retrieval env vars are fixed.
    from backend.ai.context import PoemContext
    from backend.ai.graph import graph

    results = []
    for case in cases:
        work = current_works[case["id"]]
        context = case["input"]["context"]

        result = graph.invoke(
            {
                "poem": work["content"],
                "question": case["input"]["question"],
                "selection": case["input"]["selection"],
                "context": PoemContext(
                    id=work["work_id"],
                    title=context["title"],
                    author=context.get("author"),
                    dynasty=context.get("dynasty"),
                ),
                "history": case["input"].get("history", []),
            }
        )

        reply = result.get("reply") or ""
        events = parse_tool_events(result.get("tool_results") or [])
        retrieval_events = [
            event
            for event in events
            if event.get("evidence_type") == "text_retrieval"
        ]
        target = case["target"]
        results.append(
            {
                "case_id": case["id"],
                "current_work_id": work["work_id"],
                "question": case["input"]["question"],
                "tool_count": result.get("tool_count", 0),
                "tool_events": events,
                "retrieval_queries": [
                    event.get("query")
                    for event in retrieval_events
                ],
                "used_text_retrieval": bool(retrieval_events),
                "target_answer_anchor_visible": any(
                    anchor in reply
                    for anchor in target.get("answer_anchors", [])
                ),
                "reply": reply,
            }
        )

    report = {
        "schema_version": "1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "retrieval_url": retrieval_url,
        "cases": results,
        "note": (
            "真实 Agent + LLM + HTTP Retrieval Service smoke；"
            "不是 deterministic unit test。"
        ),
    }

    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    prefix = (
        args.output_prefix
        if args.output_prefix
        else DEFAULT_REPORT_ROOT
        / f"agent_retrieval_e2e_{stamp}"
    ).expanduser().resolve()
    prefix.parent.mkdir(parents=True, exist_ok=True)
    json_path = prefix.with_suffix(".json")
    md_path = prefix.with_suffix(".md")

    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    lines = [
        "# Agent Retrieval E2E Smoke",
        "",
        "| case | tool calls | used Text Retrieval | retrieval queries | target anchor in reply |",
        "| --- | ---: | --- | --- | --- |",
    ]
    for item in results:
        lines.append(
            "| "
            + " | ".join(
                [
                    item["case_id"],
                    str(item["tool_count"]),
                    str(item["used_text_retrieval"]),
                    " → ".join(
                        query or "?"
                        for query in item["retrieval_queries"]
                    )
                    or "—",
                    str(item["target_answer_anchor_visible"]),
                ]
            )
            + " |"
        )
        lines.extend(
            [
                "",
                f"## {item['case_id']}",
                "",
                item["reply"],
                "",
                "Tool events:",
                "",
                "~~~json",
                json.dumps(
                    item["tool_events"],
                    ensure_ascii=False,
                    indent=2,
                ),
                "~~~",
                "",
            ]
        )
    md_path.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    print(f"JSON：{json_path}")
    print(f"Markdown：{md_path}")


if __name__ == "__main__":
    main()
