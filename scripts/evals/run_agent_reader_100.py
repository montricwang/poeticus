"""Run a bounded first-pass reader-question Agent experiment; no automatic grading.

This runner deliberately uses the existing graph and its actual enabled-tool state.
It never injects the human review focus or expected tool names into the model.
Results go to the ignored private data/reports directory; each case checkpoints.

To exercise an unmerged Agent feature, execute this script with PYTHONPATH
pointing to that feature's worktree (from that directory), while --dataset
points at the current question-bank worktree.
"""
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]


def build_state(case: dict, fixtures: dict):
    from backend.ai.context import PoemContext

    source = fixtures.get(case["input"].get("fixture_id"))
    return {
        "poem": source["poem"] if source else "",
        "context": (
            PoemContext(
                id="reader-eval:" + case["id"],
                title=source["title"],
                author=source["author"],
                dynasty=source["dynasty"],
            ) if source else None
        ),
        "selection": case["input"].get("selection"),
        "question": case["input"]["question"],
        "history": [],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", type=Path, default=ROOT / "evals" / "agent_reader_100_cases.json")
    ap.add_argument("--output", type=Path, default=ROOT / "data/reports/agent_reader_100_first_pass.json")
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--count", type=int, default=100)
    ap.add_argument("--enable-cnkgraph", action="store_true")
    ap.add_argument("--env-file", type=Path, help="本地私有配置文件路径（不提交仓库）")
    args = ap.parse_args()

    if args.env_file and not args.env_file.is_file():
        raise SystemExit("指定的本地 .env 文件不存在")
    load_dotenv(args.env_file, override=False) if args.env_file else load_dotenv()
    os.environ.setdefault("LANGSMITH_TRACING", "false")
    if args.enable_cnkgraph:
        os.environ["POETICUS_CNKGRAPH_RESEARCH_TOOLS_ENABLED"] = "true"

    from backend.ai import graph as agent_graph
    from backend.ai.tools import available_tools
    from backend.ai.graph import graph, text_retrieval_client, document_retrieval
    research_enabled = bool(getattr(agent_graph, "CNKGRAPH_RESEARCH_TOOLS_ENABLED", False))
    has_research_flag = "cnkgraph_research_enabled" in inspect.signature(
        available_tools
    ).parameters
    if args.enable_cnkgraph and (not has_research_flag or not research_enabled):
        raise SystemExit("当前 Agent 代码没有启用 CNKGraph 研究工具，请检查分支与开关")
    from backend.config import LLM_MODEL, AGENT_MAX_TOOL_CALLS
    from scripts.evals.run_seed import _tool_names, _tool_trace, git_sha, prompt_sha256

    raw_dataset = args.dataset.read_bytes()
    dataset_digest = hashlib.sha256(raw_dataset).hexdigest()
    dataset = json.loads(raw_dataset)
    cases = dataset["cases"]
    assert len(cases) == 100
    tool_args = (text_retrieval_client.enabled, document_retrieval.enabled)
    if has_research_flag:
        tool_args += (research_enabled,)
    enabled_tools = [t["function"]["name"] for t in available_tools(*tool_args)]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        run = json.loads(args.output.read_text(encoding="utf-8"))
        if run["dataset_id"] != dataset["dataset_id"]:
            raise SystemExit("Output belongs to another dataset")
        if run.get("dataset_sha256", dataset_digest) != dataset_digest:
            raise SystemExit("Question dataset changed; choose a new output file")
        if run["enabled_tools"] != enabled_tools:
            raise SystemExit("Tool configuration changed; choose a new output file")
        if run["model"] != LLM_MODEL:
            raise SystemExit("LLM model changed; choose a new output file")
        run["dataset_sha256"] = dataset_digest
    else:
        run = {
            "dataset_id": dataset["dataset_id"],
            "dataset_version": dataset["dataset_version"],
            "dataset_sha256": dataset_digest,
            "model": LLM_MODEL,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "git_sha": git_sha(),
            "prompt_sha256": prompt_sha256(),
            "max_tool_calls": AGENT_MAX_TOOL_CALLS,
            "enabled_tools": enabled_tools,
            "note": "Unreviewed questions and no verified Gold. All Agent answers are provisional.",
            "results": [],
        }
    completed = {x["case_id"] for x in run["results"]}
    print("CONFIG model=", LLM_MODEL, "tools=", enabled_tools,
          "budget=", AGENT_MAX_TOOL_CALLS, "completed=", len(completed), flush=True)

    for case in cases[args.offset: args.offset + args.count]:
        if case["id"] in completed:
            continue
        started = time.perf_counter()
        record = {
            "case_id": case["id"],
            "level": case["level"],
            "topic": case["topic"],
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            response = graph.invoke(build_state(case, dataset["fixtures"]))
            answer = response.get("reply", "")
            messages = [dict(x) for x in response.get("messages", [])]
            trace = _tool_trace(messages)
            record.update({
                "status": "ok" if isinstance(answer, str) and answer.strip() else "empty_answer",
                "answer": answer,
                "tool_count": response.get("tool_count", 0),
                "tool_names": _tool_names(messages),
                "tool_calls": trace["calls"],
                "tool_results": trace["results"],
            })
        except Exception as exc:
            record.update({
                "status": "error",
                "error_type": type(exc).__name__,
                "error": str(exc)[:350],
            })
        record["elapsed_seconds"] = round(time.perf_counter() - started, 2)
        run["results"].append(record)
        args.output.write_text(
            json.dumps(run, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(
            case["id"], record["status"],
            "tool", record.get("tool_names", []),
            "elapsed", record["elapsed_seconds"], flush=True,
        )
    counts = Counter(x["status"] for x in run["results"])
    print("SUMMARY", len(run["results"]), dict(counts), "saved", args.output, flush=True)


if __name__ == "__main__":
    main()
