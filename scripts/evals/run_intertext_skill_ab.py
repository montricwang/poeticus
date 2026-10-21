"""Poeticus 互文 Skill 的可恢复 D/A/B/C 离线试验。

默认只预检；--execute 才调用现有 LangGraph / DeepSeek。
在首次 Agent 系统提示词上注入指定 Skill，绝不修改生产 Prompt。
这是“方法内容”实验，不是自主发现、动态加载或路由实验。
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import time
from typing import Iterator, cast

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = ROOT / "evals/intertext_skill_30_cases.json"
DEFAULT_OUTPUT = ROOT / "data/reports/intertext_skill_ab_30.jsonl"
SKILLS = ROOT / "skills/poetry-intertext/variants"
VARIANTS = ("D", "A", "B", "C")
NAMES = {"A": "concise", "B": "standard", "C": "detailed"}
C_REFERENCES = ("methods.md", "examples.md", "pitfalls.md")


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def skill_body(variant: str) -> str:
    if variant == "D":
        return ""
    path = SKILLS / NAMES[variant] / "SKILL.md"
    raw = path.read_text(encoding="utf-8")
    if not raw.startswith("---\n") or raw.count("---") < 2:
        raise ValueError(f"Invalid Skill frontmatter: {path}")
    body = raw.split("---", 2)[2].strip()
    if variant == "C":
        # 本阶段把 C 的参考材料全部呈现给模型。动态按需读取要等 Agent
        # 真正具备 Skill 加载器后再测，不能假装此处实现了按需加载。
        refs = SKILLS / "detailed/references"
        for filename in C_REFERENCES:
            body += "\n\n## 参考资料：" + filename + "\n\n"
            body += (refs / filename).read_text(encoding="utf-8").strip()
    return body


def validate_dataset(dataset: dict, fixtures: dict) -> None:
    from collections import Counter
    cases = dataset.get("cases")
    if not isinstance(cases, list) or len(cases) != 30:
        raise ValueError("Expected exactly 30 candidate questions")
    if not isinstance(fixtures.get("fixtures"), dict):
        raise ValueError("Missing shared fixtures")
    ids: set[str] = set()
    counts: Counter[str] = Counter()
    for case in cases:
        case_id = case["id"]
        if case_id in ids:
            raise ValueError(f"Duplicate case: {case_id}")
        ids.add(case_id)
        counts[case["category"]] += 1
        source = fixtures["fixtures"].get(case["input"]["fixture_id"])
        if not source or not source.get("poem"):
            raise ValueError(f"Missing source poem for {case_id}")
        if not str(case["input"]["question"]).strip():
            raise ValueError(f"Empty question: {case_id}")
    if sorted(counts.values()) != [5] * 6:
        raise ValueError(f"Unbalanced categories: {counts}")


def build_state(case: dict, fixtures: dict) -> dict:
    from backend.ai.context import PoemContext
    source = fixtures["fixtures"][case["input"]["fixture_id"]]
    return {
        "poem": source["poem"],
        "context": PoemContext(
            id="intertext-eval:" + case["id"],
            title=source["title"],
            author=source["author"],
            dynasty=source["dynasty"],
        ),
        "question": case["input"]["question"],
        "selection": case["input"].get("selection"),
        "history": [],
    }


@contextmanager
def injected_prompt(agent_graph: object, skill: str) -> Iterator[None]:
    """只替换当前进程的首次系统 Prompt，并确保每次恢复原函数。"""
    original = agent_graph.compose_prompt
    if skill:
        def composed(*names: str) -> str:
            base = original(*names)
            if names == ("agent_decide", "output_style"):
                return base + "\n\n【本轮加载的互文分析 Skill】\n" + skill
            return base
        agent_graph.compose_prompt = composed
    try:
        yield
    finally:
        agent_graph.compose_prompt = original


def ordered_trials(cases: list[dict], variants: tuple[str, ...]) -> list[tuple[dict, str]]:
    trials = []
    for index, case in enumerate(cases):
        arms = list(variants)
        random.Random(20261021 + index).shuffle(arms)
        trials.extend((case, arm) for arm in arms)
    return trials


def load_completed(path: Path, signature: str) -> dict[tuple[str, str], dict]:
    completed: dict[tuple[str, str], dict] = {}
    if not path.exists():
        return completed
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid checkpoint line {number}") from exc
        if record.get("run_signature") != signature:
            raise ValueError("Checkpoint configuration changed. Use a fresh output path.")
        completed[(record["case_id"], record["variant"])] = record
    return completed


def append_record(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def export_blind(output: Path, signature: str) -> None:
    completed = load_completed(output, signature)
    ok = [record for record in completed.values() if record.get("status") == "ok"]
    rng = random.Random(20261021)
    rng.shuffle(ok)
    blind = []
    key = []
    for i, record in enumerate(ok, 1):
        anonymous_id = f"answer_{i:04d}"
        blind.append({
            "answer_id": anonymous_id,
            "case_id": record["case_id"],
            "answer": record["answer"],
        })
        key.append({
            "answer_id": anonymous_id,
            "case_id": record["case_id"],
            "variant": record["variant"],
        })
    blind_path = output.with_name(output.stem + "_blind.json")
    key_path = output.with_name(output.stem + "_blind_key.json")
    blind_path.write_text(json.dumps(blind, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    key_path.write_text(json.dumps(key, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("BLIND", len(blind), "answers; answer and key files saved separately", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--pilot", action="store_true", help="Only five prespecified pilot cases")
    parser.add_argument("--execute", action="store_true", help="Explicit opt-in to billable model calls")
    parser.add_argument("--max-trials", type=int, default=0, help="Maximum new calls this invocation")
    parser.add_argument("--variants", nargs="+", choices=VARIANTS, default=list(VARIANTS))
    parser.add_argument("--require-tools", nargs="*", default=[])
    parser.add_argument("--min-tool-budget", type=int, default=0)
    parser.add_argument("--blind-export", action="store_true")
    args = parser.parse_args()

    raw = args.dataset.read_bytes()
    dataset = json.loads(raw)
    fixture_path = (ROOT / dataset["fixture_source"]).resolve()
    if not fixture_path.is_relative_to(ROOT):
        raise SystemExit("Fixture source must stay inside the repository")
    fixture_raw = fixture_path.read_bytes()
    fixtures = json.loads(fixture_raw)
    validate_dataset(dataset, fixtures)
    cases = [c for c in dataset["cases"] if not args.pilot or c["split"] == "pilot"]
    variants = tuple(dict.fromkeys(args.variants))
    skills = {arm: skill_body(arm) for arm in variants}
    trials = ordered_trials(cases, variants)
    if not args.execute:
        print("DRY RUN", "cases", len(cases), "trials", len(trials))
        print("CATEGORY", {name: sum(c["category"] == name for c in cases)
                           for name in sorted({c["category"] for c in cases})})
        print("SKILL CHARS", {name: len(body) for name, body in skills.items()})
        print("No model calls. Literature source checkpoints still require human review.")
        return

    if args.env_file and not args.env_file.is_file():
        raise SystemExit("Specified private .env file does not exist")
    load_dotenv(args.env_file, override=False) if args.env_file else load_dotenv()
    os.environ.setdefault("LANGSMITH_TRACING", "false")
    if not os.getenv("LLM_API_KEY"):
        raise SystemExit("LLM_API_KEY missing; no calls were made")

    from backend.ai import graph as agent_graph
    from backend.ai.graph import graph, text_retrieval_client, document_retrieval, AgentState
    from backend.ai.tools import available_tools
    from backend.config import (
        LLM_MODEL, AGENT_MAX_TOOL_CALLS, CNKGRAPH_RESEARCH_TOOLS_ENABLED,
        DEEPSEEK_WEB_TOOLS_ENABLED, CLASSIC_REFERENCE_TOOLS_ENABLED,
    )
    from scripts.evals.run_seed import _tool_names, _tool_trace, prompt_sha256

    if AGENT_MAX_TOOL_CALLS < args.min_tool_budget:
        raise SystemExit(f"Actual tool budget {AGENT_MAX_TOOL_CALLS} is below required {args.min_tool_budget}")
    flags = (
        text_retrieval_client.enabled, document_retrieval.enabled,
        CNKGRAPH_RESEARCH_TOOLS_ENABLED, DEEPSEEK_WEB_TOOLS_ENABLED,
        CLASSIC_REFERENCE_TOOLS_ENABLED,
    )
    enabled_tools = [x["function"]["name"] for x in available_tools(*flags)]
    missing_tools = sorted(set(args.require_tools) - set(enabled_tools))
    if missing_tools:
        raise SystemExit("Missing registered tools: " + ", ".join(missing_tools))

    config = {
        "dataset_id": dataset["dataset_id"],
        "dataset_sha256": digest(raw),
        "fixtures_sha256": digest(fixture_raw),
        "skill_sha256": {arm: digest(skills[arm].encode("utf-8")) for arm in variants},
        "model": LLM_MODEL,
        "max_tool_calls": AGENT_MAX_TOOL_CALLS,
        "enabled_tools": enabled_tools,
        "prompt_sha256": prompt_sha256(),
        "variants": list(variants),
        "skill_loader": "test_only_system_prompt_injection",
        "c_reference_strategy": "all_references_inline",
    }
    signature = digest(json.dumps(config, sort_keys=True, ensure_ascii=False).encode("utf-8"))
    completed = load_completed(args.output, signature)
    print("CONFIG", LLM_MODEL, "tools", enabled_tools, "budget",
          AGENT_MAX_TOOL_CALLS, "resumed", len(completed), flush=True)
    attempted = 0
    for case, variant in trials:
        key = (case["id"], variant)
        if key in completed and (completed[key]["status"] == "ok"
                                  or completed[key]["status"] == "empty_answer"):
            continue
        if key in completed:
            # Errors are not silently rerun, keeping retry scope explicit.
            continue
        if args.max_trials and attempted >= args.max_trials:
            break
        started = time.perf_counter()
        record = {
            "run_signature": signature,
            "case_id": case["id"], "category": case["category"],
            "variant": variant,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "model": LLM_MODEL, "tool_budget": AGENT_MAX_TOOL_CALLS,
        }
        try:
            with injected_prompt(agent_graph, skills[variant]):
                response = graph.invoke(cast(AgentState, build_state(case, fixtures)))
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
            record.update({"status": "error", "error_type": type(exc).__name__,
                           "error": str(exc)[:350]})
        record["elapsed_seconds"] = round(time.perf_counter() - started, 2)
        append_record(args.output, record)
        attempted += 1
        print(case["id"], variant, record["status"], record["elapsed_seconds"], flush=True)
    if args.blind_export:
        export_blind(args.output, signature)
    print("SUMMARY", "attempted", attempted, "saved", args.output, flush=True)


if __name__ == "__main__":
    main()
