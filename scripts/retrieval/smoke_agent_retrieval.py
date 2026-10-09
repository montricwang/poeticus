"""执行真实 Agent → HTTP Retrieval Service → Agent 的冒烟测试。

前提：
1. 在另一终端启动本地服务：
       python -m scripts.retrieval.run_serving
2. 在 .env 中配置有效的 LLM_API_KEY。

本脚本调用真实 Agent 和真实 Retrieval Service。
为覆盖正常的全文重复排除逻辑，会先将测试片段定位到完整的
Corpus Work，再交给 Agent 发起检索。"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Mapping, Sequence
from typing import Literal, NotRequired, TypedDict

from pydantic import ConfigDict, TypeAdapter, with_config

from backend.data_paths import RETRIEVAL_REPORTS_ROOT, RETRIEVAL_ROOT

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CASES = ROOT / "evals/retrieval_increment_cases.json"
DEFAULT_REPORT_ROOT = RETRIEVAL_REPORTS_ROOT
DEFAULT_CASE_IDS = (
    "longtail_luyou_dufu_gull",
    "compressed_jiangkui_dumu_qinglou",
)
DEFAULT_METADATA_MANIFEST = RETRIEVAL_ROOT / "serving/retrieval_metadata.manifest.json"


class SmokeContext(TypedDict):
    title: str
    author: str | None
    dynasty: str | None


class SmokeHistoryMessage(TypedDict):
    role: Literal["user", "assistant"]
    content: str


class SmokeInput(TypedDict):
    poem: str
    question: str
    selection: str | None
    context: SmokeContext
    history: NotRequired[list[SmokeHistoryMessage]]


class SmokeTarget(TypedDict):
    answer_anchors: list[str]


@with_config(ConfigDict(extra="allow"))
class SmokeCase(TypedDict):
    id: str
    input: SmokeInput
    current_match_text: str
    retrieval_query: str
    target: SmokeTarget


@with_config(ConfigDict(extra="allow"))
class SmokeWork(TypedDict):
    work_id: str
    content: str
    author: str | None


class ToolEvent(TypedDict):
    tool_call_id: str | None
    status: str | None
    evidence_type: str | None
    query: str | None
    candidates: list[dict[str, object]]


_CASES_ADAPTER = TypeAdapter(list[SmokeCase])
_WORK_ADAPTER = TypeAdapter(SmokeWork)


def load_cases(path: Path, case_ids: tuple[str, ...]) -> list[SmokeCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Smoke fixtures must be a JSON object")
    cases = _CASES_ADAPTER.validate_python(payload.get("cases"))
    by_id = {item["id"]: item for item in cases}
    missing = [case_id for case_id in case_ids if case_id not in by_id]
    if missing:
        raise ValueError(
            "Smoke case 不存在：" + ", ".join(missing)
        )
    return [by_id[case_id] for case_id in case_ids]


def resolve_full_current_works(
    work_path: Path,
    cases: list[SmokeCase],
) -> dict[str, SmokeWork]:
    """根据作者和已知当前文本，为每个 Case 定位一份完整的当前 Work。"""
    unresolved = {case["id"] for case in cases}
    resolved: dict[str, SmokeWork] = {}

    with work_path.open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            work = json.loads(line)
            if not isinstance(work, dict):
                continue
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
                resolved[case_id] = _WORK_ADAPTER.validate_python(work)
                unresolved.remove(case_id)

            if not unresolved:
                break

    if unresolved:
        raise ValueError(
            "无法从 Corpus 解析当前完整作品："
            + ", ".join(sorted(unresolved))
        )
    return resolved


def parse_tool_events(tool_results: Sequence[Mapping[str, object]]) -> list[ToolEvent]:
    events: list[ToolEvent] = []
    for item in tool_results:
        content = item.get("content")
        if not isinstance(content, str):
            continue
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            payload = {"status": "invalid_json", "raw": content[:500]}

        if not isinstance(payload, dict):
            payload = {"status": "invalid_payload"}
        candidates = payload.get("candidates")
        preview: list[dict[str, object]] = []
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

        raw_status = payload.get("status")
        raw_type = payload.get("evidence_type")
        raw_query = payload.get("query")
        raw_call_id = item.get("id")
        events.append(
            {
                "tool_call_id": raw_call_id if isinstance(raw_call_id, str) else None,
                "status": raw_status if isinstance(raw_status, str) else None,
                "evidence_type": raw_type if isinstance(raw_type, str) else None,
                "query": raw_query if isinstance(raw_query, str) else None,
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

    # Agent 客户端在模块导入时读取这些环境变量。
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

    # 必须先设置好 Retrieval 环境变量，再导入 Agent 相关模块。
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
        first_tool_type = (
            events[0].get("evidence_type")
            if events
            else None
        )
        target = case["target"]
        results.append(
            {
                "case_id": case["id"],
                "current_work_id": work["work_id"],
                "question": case["input"]["question"],
                "tool_count": result.get("tool_count", 0),
                "tool_events": events,
                "first_tool_type": first_tool_type,
                "text_retrieval_call_count": len(retrieval_events),
                "retrieval_queries": [
                    event.get("query")
                    for event in retrieval_events
                ],
                "used_text_retrieval": bool(retrieval_events),
                "routing_policy_pass": (
                    first_tool_type == "text_retrieval"
                ),
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
        "| case | tool calls | first tool | Text Retrieval calls | routing pass | retrieval queries | target anchor in reply |",
        "| --- | ---: | --- | ---: | --- | --- | --- |",
    ]
    for item in results:
        lines.append(
            "| "
            + " | ".join(
                [
                    item["case_id"],
                    str(item["tool_count"]),
                    str(item["first_tool_type"] or "—"),
                    str(item["text_retrieval_call_count"]),
                    str(item["routing_policy_pass"]),
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
