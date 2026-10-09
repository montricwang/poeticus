"""运行 Seed Eval 的最小对照实验。

control_no_tools 与 current_agent 使用同一模型和系统 Prompt；
前者仍把当前 Tool Schema 提供给模型，但强制 tool_choice=none，
后者走正式 LangGraph Agent。
"""

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

from openai.types.chat import ChatCompletionMessageParam

from backend.ai.context import PoemContext
from backend.ai.graph import HistoryMessage, RouterState, TOOLS, _agent_user_message, graph
from backend.ai.model import client
from backend.ai.prompt_loader import compose_prompt
from backend.config import LLM_MAX_OUTPUT_TOKENS, LLM_MODEL
from evals.schema import EvalCase, EvalDataset


class ControlResult(TypedDict):
    answer: str
    tool_count: int
    evidence_count: int


class AgentTrace(TypedDict):
    calls: list[dict[str, object]]
    results: list[dict[str, object]]


class AgentResult(TypedDict):
    answer: str
    tool_count: int
    tool_names: list[str]
    evidence_count: int
    tool_calls: list[dict[str, object]]
    tool_results: list[dict[str, object]]


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = ROOT / "evals" / "seed_cases.json"


def load_dataset(path: Path) -> EvalDataset:
    return EvalDataset.model_validate_json(path.read_text(encoding="utf-8"))


def graph_state(case: EvalCase) -> RouterState:
    context = PoemContext(
        id=f"eval:{case.id}",
        title=case.input.context.title,
        author=case.input.context.author,
        dynasty=case.input.context.dynasty,
    )
    history: list[HistoryMessage] = [
        {"role": message.role, "content": message.content}
        for message in case.input.history
    ]
    return {
        "poem": case.input.poem,
        "question": case.input.question,
        "selection": case.input.selection,
        "context": context,
        "history": history,
    }


def run_control_no_tools(case: EvalCase) -> ControlResult:
    state = graph_state(case)
    system_prompt = compose_prompt("agent_decide", "output_style")
    messages: list[ChatCompletionMessageParam] = [
        {"role": "system", "content": system_prompt}
    ]
    for history in state.get("history", []):
        if history["role"] == "user":
            messages.append({"role": "user", "content": history["content"]})
        else:
            messages.append({"role": "assistant", "content": history["content"]})
    messages.append({"role": "user", "content": _agent_user_message(state)})

    response = client.chat.completions.create(
        model=LLM_MODEL,
        max_tokens=LLM_MAX_OUTPUT_TOKENS,
        messages=messages,
        tools=TOOLS,
        tool_choice="none",
        temperature=0,
        extra_body={"thinking": {"type": "disabled"}},
    )

    if not response.choices or not response.choices[0].message.content:
        raise RuntimeError("control_no_tools 没有返回有效回答")

    return {
        "answer": response.choices[0].message.content,
        "tool_count": 0,
        "evidence_count": 0,
    }


def _tool_names(messages: list[dict[str, object]]) -> list[str]:
    names: list[str] = []
    for message in messages:
        calls = message.get("tool_calls")
        if not isinstance(calls, list):
            continue
        for call in calls:
            if not isinstance(call, dict):
                continue
            function = call.get("function")
            if not isinstance(function, dict):
                continue
            name = function.get("name")
            if isinstance(name, str):
                names.append(name)
    return names


def _parse_json_object(value):
    if not isinstance(value, str):
        return value
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return value
    return parsed


def _evidence_preview(item: dict[str, object]) -> dict[str, object]:
    source = item.get("source")
    source_preview = None
    if isinstance(source, dict):
        source_preview = {
            key: source.get(key)
            for key in ("title", "author", "work")
            if source.get(key)
        }

    text = item.get("text")
    if isinstance(text, str):
        text = text[:240]

    preview: dict[str, object] = {
        "anchor": item.get("anchor"),
        "provider": item.get("provider"),
        "status": item.get("status"),
        "text_preview": text,
    }
    if source_preview:
        preview["source"] = source_preview
    return preview


def _tool_trace(messages: list[dict[str, object]]) -> AgentTrace:
    calls: list[dict[str, object]] = []
    results: list[dict[str, object]] = []

    for message in messages:
        if message.get("role") == "assistant":
            tool_calls = message.get("tool_calls")
            for call in tool_calls if isinstance(tool_calls, list) else []:
                if not isinstance(call, dict):
                    continue
                function = call.get("function")
                if not isinstance(function, dict):
                    continue
                calls.append(
                    {
                        "id": call.get("id"),
                        "name": function.get("name"),
                        "arguments": _parse_json_object(
                            function.get("arguments")
                        ),
                    }
                )

        if message.get("role") == "tool":
            payload = _parse_json_object(message.get("content"))
            result: dict[str, object] = {
                "tool_call_id": message.get("tool_call_id"),
            }

            if isinstance(payload, dict):
                evidences = payload.get("evidences") or []
                result.update(
                    {
                        "status": payload.get("status"),
                        "query": payload.get("query"),
                        "evidence_count": (
                            len(evidences)
                            if isinstance(evidences, list)
                            else 0
                        ),
                        "evidences": [
                            _evidence_preview(item)
                            for item in evidences
                            if isinstance(item, dict)
                        ],
                    }
                )
                if payload.get("message"):
                    result["message"] = payload.get("message")
            else:
                result["raw_content"] = payload

            results.append(result)

    return {
        "calls": calls,
        "results": results,
    }


def run_current_agent(case: EvalCase) -> AgentResult:
    result = graph.invoke(graph_state(case))
    answer = result.get("reply")
    if not isinstance(answer, str) or not answer.strip():
        raise RuntimeError("current_agent 没有返回有效回答")

    messages: list[dict[str, object]] = [
        dict(message) for message in (result.get("messages") or [])
    ]
    trace = _tool_trace(messages)

    return {
        "answer": answer,
        "tool_count": result.get("tool_count", 0),
        "tool_names": _tool_names(messages),
        "evidence_count": len(result.get("evidences") or []),
        "tool_calls": trace["calls"],
        "tool_results": trace["results"],
    }


def git_sha() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def prompt_sha256() -> str:
    prompt = compose_prompt("agent_decide", "output_style")
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--case", action="append", dest="case_ids")
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dataset = load_dataset(args.dataset)

    selected = [
        case
        for case in dataset.cases
        if not args.case_ids or case.id in set(args.case_ids)
    ]

    if args.case_ids:
        found = {case.id for case in selected}
        missing = set(args.case_ids) - found
        if missing:
            raise SystemExit(f"未知 case id: {', '.join(sorted(missing))}")

    case_results: list[dict[str, object]] = []
    run = {
        "dataset_id": dataset.dataset_id,
        "dataset_version": dataset.dataset_version,
        "git_sha": git_sha(),
        "model": LLM_MODEL,
        "prompt_sha256": prompt_sha256(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "cases": case_results,
    }

    for case in selected:
        print(f"\n=== {case.id} ===")
        control = run_control_no_tools(case)
        agent = run_current_agent(case)

        print("\n[control_no_tools]")
        print(control["answer"])
        print("\n[current_agent]")
        print(agent["answer"])
        result_summary = [
            {
                "query": item.get("query"),
                "status": item.get("status"),
                "evidence_count": item.get("evidence_count"),
            }
            for item in agent["tool_results"]
        ]
        print(
            f"\nprocess: tools={agent['tool_names']} "
            f"tool_count={agent['tool_count']} "
            f"evidence_count={agent['evidence_count']} "
            f"tool_results={result_summary}"
        )

        case_results.append(
            {
                "case_id": case.id,
                "expected": case.expected.model_dump(),
                "control_no_tools": control,
                "current_agent": agent,
            }
        )

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(run, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"\n已保存：{args.output}")


if __name__ == "__main__":
    main()
