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

from backend.ai.context import PoemContext
from backend.ai.graph import TOOLS, _agent_user_message, graph
from backend.ai.model import client
from backend.ai.prompt_loader import compose_prompt
from backend.config import LLM_MAX_OUTPUT_TOKENS, LLM_MODEL
from evals.schema import EvalCase, EvalDataset


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = ROOT / "evals" / "seed_cases.json"


def load_dataset(path: Path) -> EvalDataset:
    return EvalDataset.model_validate_json(path.read_text(encoding="utf-8"))


def graph_state(case: EvalCase) -> dict:
    context = PoemContext(
        id=f"eval:{case.id}",
        title=case.input.context.title,
        author=case.input.context.author,
        dynasty=case.input.context.dynasty,
    )
    return {
        "poem": case.input.poem,
        "question": case.input.question,
        "selection": case.input.selection,
        "context": context,
        "history": [message.model_dump() for message in case.input.history],
    }


def run_control_no_tools(case: EvalCase) -> dict:
    state = graph_state(case)
    system_prompt = compose_prompt("agent_decide", "output_style")
    messages = [{"role": "system", "content": system_prompt}]

    messages.extend(state["history"])
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


def _tool_names(messages: list[dict]) -> list[str]:
    names: list[str] = []
    for message in messages:
        for call in message.get("tool_calls") or []:
            function = call.get("function") or {}
            name = function.get("name")
            if isinstance(name, str):
                names.append(name)
    return names


def run_current_agent(case: EvalCase) -> dict:
    result = graph.invoke(graph_state(case))
    answer = result.get("reply")
    if not isinstance(answer, str) or not answer.strip():
        raise RuntimeError("current_agent 没有返回有效回答")

    return {
        "answer": answer,
        "tool_count": result.get("tool_count", 0),
        "tool_names": _tool_names(result.get("messages") or []),
        "evidence_count": len(result.get("evidences") or []),
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

    run = {
        "dataset_id": dataset.dataset_id,
        "dataset_version": dataset.dataset_version,
        "git_sha": git_sha(),
        "model": LLM_MODEL,
        "prompt_sha256": prompt_sha256(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "cases": [],
    }

    for case in selected:
        print(f"\n=== {case.id} ===")
        control = run_control_no_tools(case)
        agent = run_current_agent(case)

        print("\n[control_no_tools]")
        print(control["answer"])
        print("\n[current_agent]")
        print(agent["answer"])
        print(
            f"\nprocess: tools={agent['tool_names']} "
            f"tool_count={agent['tool_count']} "
            f"evidence_count={agent['evidence_count']}"
        )

        run["cases"].append(
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
