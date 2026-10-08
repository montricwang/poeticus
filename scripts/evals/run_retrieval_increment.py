"""Compare standalone-LLM knowledge with local full-corpus Retrieval.

This is the first small increment-value eval, not a final RAG benchmark.

For each fixed case it records:
1. standalone_llm: no Agent prompt, no Tool Schema;
2. tool_augmented_llm: same plain input plus one local Retrieval function tool;
3. hybrid_retrieval diagnostics for the canonical fixed query;
4. a lightweight navigation heuristic, never a Ground Truth score.

The script writes detailed JSON plus a readable Markdown report so large
results can be uploaded directly instead of copied through chat.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from backend.data_paths import RETRIEVAL_REPORTS_ROOT
from typing import Callable, Literal

from pydantic import BaseModel, ConfigDict, Field

from evals.schema import EvalInput
from scripts.retrieval.exact_search import DEFAULT_DATA_ROOT, DEFAULT_WORKS
from scripts.retrieval.hybrid_eval import evaluate_hybrid
from scripts.retrieval.lexical_bm25 import DEFAULT_INDEX_ROOT


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = ROOT / "evals" / "retrieval_increment_cases.json"
DEFAULT_REPORT_ROOT = RETRIEVAL_REPORTS_ROOT

DEFAULT_SENTENCE_ARTIFACT = (
    DEFAULT_DATA_ROOT / "embeddings/qwen3_0.6b_sentence_1024"
)
DEFAULT_CLAUSE_ARTIFACT = (
    DEFAULT_DATA_ROOT / "embeddings/qwen3_0.6b_clause_1024"
)
DEFAULT_SENTENCE_FAISS = (
    DEFAULT_DATA_ROOT
    / "faiss/qwen3_0.6b_sentence_1024_ivfpq_nlist512_m256_b8"
)
DEFAULT_CLAUSE_FAISS = (
    DEFAULT_DATA_ROOT
    / "faiss/qwen3_0.6b_clause_1024_ivfpq_nlist512_m256_b8"
)
DEFAULT_SENTENCE_BM25 = DEFAULT_INDEX_ROOT / "bm25_sentence_2_3"

LOCAL_RETRIEVAL_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_predecessor_texts",
            "description": (
                "在本地古典诗词 Corpus 中搜索可能对应当前文本的前代诗文候选。"
                "适合查询成句、改写、拆取重组、意象或措辞相近的前代文本。"
                "返回的是候选证据，不等于已经证明化用关系。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": (
                            "要检索来源的诗句或短文本。优先提交真正需要比较的原文。"
                        ),
                    }
                },
                "required": ["text"],
                "additionalProperties": False,
            },
        },
    }
]


class RetrievalTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    author: str = Field(min_length=1)
    text: str = Field(min_length=1)
    answer_anchors: list[str] = Field(min_length=1)


class RetrievalIncrementCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]+$")
    tier: Literal["known_control", "mid_distance", "long_tail_probe"]
    relation: str = Field(min_length=1)
    input: EvalInput
    retrieval_query: str = Field(min_length=1)
    current_match_text: str = Field(min_length=1)
    target: RetrievalTarget
    rationale: str = Field(min_length=1)
    agent_loop_probe: bool = False


class RetrievalIncrementDataset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"]
    dataset_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]+$")
    dataset_version: int = Field(ge=1)
    status: Literal["draft", "active"]
    cases: list[RetrievalIncrementCase] = Field(min_length=1)


def load_dataset(path: Path) -> RetrievalIncrementDataset:
    return RetrievalIncrementDataset.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def git_sha() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _content_fingerprint(content: str) -> str:
    """High-confidence duplicate key: exact text after whitespace removal."""
    normalized = "".join(content.split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def scan_work_matches(
    *,
    work_path: Path,
    cases: list[RetrievalIncrementCase],
) -> dict[str, dict]:
    """Resolve current / target works in one pass through Work JSONL."""
    matches = {
        case.id: {"current": [], "target": []}
        for case in cases
    }

    with work_path.open(encoding="utf-8") as stream:
        for line_no, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                work = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Work JSONL 第 {line_no} 行无法解析"
                ) from exc

            author = work.get("author")
            content = work.get("content", "")
            if not isinstance(content, str):
                continue

            for case in cases:
                if (
                    author == case.input.context.author
                    and case.current_match_text in content
                ):
                    matches[case.id]["current"].append(
                        {
                            "work_id": work["work_id"],
                            "title": work.get("title"),
                            "author": author,
                            "dynasty": work.get("dynasty"),
                            "content_fingerprint": _content_fingerprint(content),
                        }
                    )

                if (
                    author == case.target.author
                    and case.target.text in content
                ):
                    matches[case.id]["target"].append(
                        {
                            "work_id": work["work_id"],
                            "title": work.get("title"),
                            "author": author,
                            "dynasty": work.get("dynasty"),
                            "content_fingerprint": _content_fingerprint(content),
                        }
                    )

    return matches


def choose_current_work_id(
    case: RetrievalIncrementCase,
    candidates: list[dict],
) -> str | None:
    if not candidates:
        return None

    title = case.input.context.title
    exact_title = [
        item for item in candidates
        if item.get("title") == title
    ]
    chosen = exact_title[0] if exact_title else candidates[0]
    return chosen["work_id"]


def choose_current_work_ids(
    case: RetrievalIncrementCase,
    candidates: list[dict],
) -> set[str]:
    """Return exact-content aliases of the chosen current Work.

    We deliberately avoid fuzzy title/content dedup here. Only records with the
    same author (already guaranteed by scan_work_matches) and identical content
    after whitespace removal are treated as self-hit aliases.
    """
    chosen_id = choose_current_work_id(case, candidates)
    if chosen_id is None:
        return set()

    chosen = next(
        item for item in candidates
        if item["work_id"] == chosen_id
    )
    fingerprint = chosen.get("content_fingerprint")
    if not fingerprint:
        return {chosen_id}

    return {
        item["work_id"]
        for item in candidates
        if item.get("content_fingerprint") == fingerprint
    }


def _plain_user_message(case: RetrievalIncrementCase) -> str:
    context = case.input.context
    return (
        f"作品：{context.title}\n"
        f"作者：{context.author or '未知'}\n"
        f"朝代：{context.dynasty or '未知'}\n\n"
        f"原文：\n{case.input.poem}\n\n"
        f"当前选区：\n"
        f"{case.input.selection or '（未选择任何原文）'}\n\n"
        f"问题：\n{case.input.question}"
    )


def _answer_signal(
    case: RetrievalIncrementCase,
    answer: str,
) -> dict:
    anchor_hits = [
        anchor
        for anchor in case.target.answer_anchors
        if anchor in answer
    ]
    author_hit = case.target.author in answer
    return {
        "target_author_mentioned": author_hit,
        "target_anchor_hits": anchor_hits,
        "target_signal": author_hit and bool(anchor_hits),
    }


def _plain_messages(case: RetrievalIncrementCase) -> list[dict]:
    messages = [
        message.model_dump()
        for message in case.input.history
    ]
    messages.append(
        {
            "role": "user",
            "content": _plain_user_message(case),
        }
    )
    return messages


def run_standalone_llm(case: RetrievalIncrementCase) -> dict:
    """Run the model with no Agent prompt and no Tool Schema."""
    from backend.ai.model import client
    from backend.config import LLM_MAX_OUTPUT_TOKENS, LLM_MODEL

    response = client.chat.completions.create(
        model=LLM_MODEL,
        max_tokens=LLM_MAX_OUTPUT_TOKENS,
        messages=_plain_messages(case),
        temperature=0,
        extra_body={"thinking": {"type": "disabled"}},
    )
    if not response.choices or not response.choices[0].message.content:
        raise RuntimeError("standalone_llm 没有返回有效回答")

    answer = response.choices[0].message.content
    return {
        "model": LLM_MODEL,
        "answer": answer,
        **_answer_signal(case, answer),
    }


def compact_tool_result(result: dict, *, max_items: int = 8) -> dict:
    """Expose only product-facing candidates to the tool-using model.

    Probe / Ground Truth metadata is intentionally excluded so the model never
    sees the evaluation target through the tool result.
    """
    candidates = []
    for item in (result.get("ranking") or [])[:max_items]:
        evidence = item.get("best_evidence") or {}
        candidates.append(
            {
                "rank": item.get("rank"),
                "title": item.get("title"),
                "author": item.get("author"),
                "dynasty": item.get("dynasty"),
                "text": evidence.get("text"),
                "query": evidence.get("query"),
                "channel": evidence.get("channel"),
                "support_count": item.get("support_count"),
                "chronology_status": item.get("chronology_status"),
            }
        )
    return {
        "status": "ok" if candidates else "no_hit",
        "candidates": candidates,
        "note": (
            "这些结果只是文本相似候选，不自动证明引用、化用或影响关系；"
            "请结合年代、文本对应关系和当前问题自行判断。"
        ),
    }


def run_tool_augmented_llm(
    case: RetrievalIncrementCase,
    *,
    search_tool: Callable[[str], dict],
) -> dict:
    """Run one plain model with one local Retrieval function-call round trip.

    No LangGraph, no Agent system prompt, no autonomous multi-step loop.
    The only added capability relative to run_standalone_llm is the Tool Schema.
    """
    from backend.ai.model import client
    from backend.config import LLM_MAX_OUTPUT_TOKENS, LLM_MODEL

    messages = _plain_messages(case)
    first = client.chat.completions.create(
        model=LLM_MODEL,
        max_tokens=LLM_MAX_OUTPUT_TOKENS,
        messages=messages,
        tools=LOCAL_RETRIEVAL_TOOLS,
        tool_choice="auto",
        temperature=0,
        extra_body={"thinking": {"type": "disabled"}},
    )
    if not first.choices:
        raise RuntimeError("tool_augmented_llm 第一轮没有返回结果")

    message = first.choices[0].message
    calls = list(message.tool_calls or [])
    if not calls:
        answer = message.content or ""
        if not answer.strip():
            raise RuntimeError("tool_augmented_llm 既没有回答也没有调用工具")
        return {
            "model": LLM_MODEL,
            "answer": answer,
            "tool_used": False,
            "tool_query": None,
            "tool_result": None,
            **_answer_signal(case, answer),
        }

    call = calls[0]
    if call.type != "function" or call.function.name != "search_predecessor_texts":
        raise RuntimeError(f"tool_augmented_llm 调用了未知工具：{call.function.name}")

    try:
        arguments = json.loads(call.function.arguments)
    except json.JSONDecodeError as exc:
        raise RuntimeError("tool_augmented_llm 返回了无效工具参数") from exc
    query = arguments.get("text") if isinstance(arguments, dict) else None
    if not isinstance(query, str) or not query.strip() or len(query) > 120:
        raise RuntimeError("tool_augmented_llm 的 Retrieval query 无效")
    query = query.strip()

    tool_result = search_tool(query)
    assistant_tool_call = {
        "role": "assistant",
        "content": message.content or "",
        "tool_calls": [
            {
                "id": call.id,
                "type": "function",
                "function": {
                    "name": call.function.name,
                    "arguments": call.function.arguments,
                },
            }
        ],
    }
    messages.append(assistant_tool_call)
    messages.append(
        {
            "role": "tool",
            "tool_call_id": call.id,
            "content": json.dumps(
                tool_result,
                ensure_ascii=False,
            ),
        }
    )

    final = client.chat.completions.create(
        model=LLM_MODEL,
        max_tokens=LLM_MAX_OUTPUT_TOKENS,
        messages=messages,
        tools=LOCAL_RETRIEVAL_TOOLS,
        tool_choice="none",
        temperature=0,
        extra_body={"thinking": {"type": "disabled"}},
    )
    if not final.choices or not final.choices[0].message.content:
        raise RuntimeError("tool_augmented_llm 工具返回后没有生成最终回答")

    answer = final.choices[0].message.content
    return {
        "model": LLM_MODEL,
        "answer": answer,
        "tool_used": True,
        "tool_query": query,
        "ignored_extra_tool_calls": max(0, len(calls) - 1),
        "tool_result": tool_result,
        **_answer_signal(case, answer),
    }

def tool_target_support(
    *,
    result: dict | None,
    target_work_ids: set[str],
    max_items: int = 8,
) -> tuple[bool | None, int | None]:
    """Check whether the exact target Work was actually shown to the LLM."""
    if result is None:
        return None, None
    for rank, item in enumerate((result.get("ranking") or [])[:max_items], 1):
        if item.get("work_id") in target_work_ids:
            return True, rank
    return False, None


def _best_rank(probes: list[dict], field: str) -> int | None:
    ranks = [
        probe.get(field)
        for probe in probes
        if isinstance(probe.get(field), int)
    ]
    return min(ranks) if ranks else None


def summarize_retrieval(result: dict) -> dict:
    probes = result.get("probes") or []
    best_eligible = _best_rank(probes, "eligible_rank")
    best_fused = _best_rank(probes, "fused_rank")

    return {
        "best_fused_rank": best_fused,
        "best_eligible_rank": best_eligible,
        "target_in_top5": (
            best_eligible is not None
            and best_eligible <= 5
        ),
        "target_in_top20": (
            best_eligible is not None
            and best_eligible <= 20
        ),
        "candidate_pool": result.get("candidate_pool"),
        "channels": result.get("channels"),
        "query_plan": result.get("query_plan"),
        "probes": probes,
        "top_candidates": result.get("ranking", [])[:10],
    }


def comparison_bucket(
    *,
    standalone_signal: bool | None,
    tool_signal: bool | None,
    target_supported_by_tool: bool | None,
    eligible_rank: int | None,
    agent_loop_probe: bool,
) -> str:
    """Navigation label only; never a correctness score."""
    retrieval_top20 = (
        eligible_rank is not None
        and eligible_rank <= 20
    )

    if standalone_signal is True and tool_signal is True:
        if target_supported_by_tool is True:
            return "standalone_knows_tool_confirms"
        return "standalone_already_knows"
    if standalone_signal is False and tool_signal is True:
        if target_supported_by_tool is True:
            return "tool_increment_candidate"
        return "answer_changed_without_target_evidence"
    if standalone_signal is True and tool_signal is False:
        if agent_loop_probe:
            return "single_shot_agent_loop_candidate"
        return "tool_regression_candidate"
    if standalone_signal is False and tool_signal is False and retrieval_top20:
        return "retrieval_found_model_failed"
    if standalone_signal is False and tool_signal is False:
        return "both_gap"
    return "partial_run"

def _md_escape(value: object) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def render_markdown(run: dict) -> str:
    lines = [
        "# Retrieval Increment Eval",
        "",
        "> 本轮比较：③ 独立 LLM vs ④ 只有一个本地 Text Retrieval Tool 的模型。",
        "> 同时保留 Retrieval 本身的候选排名诊断；字符串命中只用于导航，不是自动判分。",
        "",
        "## Summary",
        "",
        "| Case | 档位 | 独立 LLM 目标信号 | 工具增强 LLM 目标信号 | Tool used | 目标证据在 Tool 中 | Tool target rank | Retrieval eligible rank | 导航标签 |",
        "| --- | --- | --- | --- | --- | --- | ---: | ---: | --- |",
    ]

    for item in run["cases"]:
        standalone = item.get("standalone_llm")
        tool = item.get("tool_augmented_llm")
        retrieval = item.get("retrieval")
        standalone_signal = None if not isinstance(standalone, dict) else standalone.get("target_signal")
        tool_signal = None if not isinstance(tool, dict) else tool.get("target_signal")
        tool_used = None if not isinstance(tool, dict) else tool.get("tool_used")
        rank = None if not isinstance(retrieval, dict) else retrieval.get("best_eligible_rank")
        lines.append(
            "| "
            + " | ".join(
                [
                    _md_escape(item["case_id"]),
                    _md_escape(item["tier"]),
                    _md_escape(standalone_signal),
                    _md_escape(tool_signal),
                    _md_escape(tool_used),
                    _md_escape(None if not isinstance(tool, dict) else tool.get("target_supported_by_tool")),
                    _md_escape(None if not isinstance(tool, dict) else tool.get("target_rank_in_tool_candidates")),
                    _md_escape(rank),
                    _md_escape(item["comparison_bucket"]),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## How to read",
            "",
            "- 独立 LLM 没有 Agent Prompt，也没有 Tool Schema。",
            "- 工具增强 LLM 没有 LangGraph / Agent 编排，只多一个 search_predecessor_texts function tool，当前实验最多执行一次。",
            "- target_signal 只是作者名 + 目标特征短语的字符串命中，用于快速导航，不是自动判对错。",
            "- Retrieval rank 是现有 Hybrid + RRF + Eligibility 下的 Work 排名，不等于文学关系概率。",
            "",
        ]
    )

    for item in run["cases"]:
        lines.extend(
            [
                f"## {item['case_id']}",
                "",
                f"- Tier: {item['tier']}",
                f"- Relation: {item['relation']}",
                f"- Canonical Retrieval Query: {item['retrieval_query']}",
                f"- Expected target: {item['target']['author']} — {item['target']['text']}",
                f"- Comparison bucket: {item['comparison_bucket']}",
                "",
            ]
        )

        standalone = item.get("standalone_llm")
        lines.extend(["### ③ 独立 LLM", ""])
        if isinstance(standalone, dict):
            lines.extend(
                [
                    f"- target_author_mentioned: {standalone.get('target_author_mentioned')}",
                    f"- target_anchor_hits: {standalone.get('target_anchor_hits')}",
                    "",
                    standalone.get("answer", ""),
                    "",
                ]
            )
        else:
            lines.extend([f"运行失败：{item.get('standalone_llm_error')}", ""])

        tool = item.get("tool_augmented_llm")
        lines.extend(["### ④ 工具增强 LLM", ""])
        if isinstance(tool, dict):
            lines.extend(
                [
                    f"- tool_used: {tool.get('tool_used')}",
                    f"- tool_query: {tool.get('tool_query')}",
                    f"- target_supported_by_tool: {tool.get('target_supported_by_tool')}",
                    f"- target_rank_in_tool_candidates: {tool.get('target_rank_in_tool_candidates')}",
                    f"- target_author_mentioned: {tool.get('target_author_mentioned')}",
                    f"- target_anchor_hits: {tool.get('target_anchor_hits')}",
                    "",
                    tool.get("answer", ""),
                    "",
                ]
            )
            if tool.get("tool_result"):
                lines.extend(["#### Tool candidates", ""])
                for candidate in tool["tool_result"].get("candidates") or []:
                    lines.append(
                        f"- #{candidate.get('rank')} "
                        f"{candidate.get('author')}《{candidate.get('title')}》："
                        f"{candidate.get('text')}"
                    )
                lines.append("")
        else:
            lines.extend([f"运行失败：{item.get('tool_augmented_llm_error')}", ""])

        retrieval = item.get("retrieval")
        lines.extend(["### Retrieval 诊断", ""])
        if isinstance(retrieval, dict):
            lines.extend(
                [
                    f"- best_fused_rank: {retrieval.get('best_fused_rank')}",
                    f"- best_eligible_rank: {retrieval.get('best_eligible_rank')}",
                    "",
                    "| rank | author | title | best evidence | support_count |",
                    "| ---: | --- | --- | --- | ---: |",
                ]
            )
            for candidate in retrieval.get("top_candidates") or []:
                evidence = candidate.get("best_evidence") or {}
                evidence_text = (
                    f"{evidence.get('channel')} #{evidence.get('rank')}: "
                    f"{evidence.get('text')}"
                )
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            _md_escape(candidate.get("rank")),
                            _md_escape(candidate.get("author")),
                            _md_escape(candidate.get("title")),
                            _md_escape(evidence_text),
                            _md_escape(candidate.get("support_count")),
                        ]
                    )
                    + " |"
                )
            lines.append("")
        else:
            lines.extend([f"运行失败：{item.get('retrieval_error')}", ""])

    return "\n".join(lines).rstrip() + "\n"

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="比较独立 LLM 与工具增强 LLM"
    )
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--case", action="append", dest="case_ids")
    parser.add_argument("--works", type=Path, default=DEFAULT_WORKS)
    parser.add_argument(
        "--sentence-artifact-dir",
        type=Path,
        default=DEFAULT_SENTENCE_ARTIFACT,
    )
    parser.add_argument(
        "--sentence-index-dir",
        type=Path,
        default=DEFAULT_SENTENCE_FAISS,
    )
    parser.add_argument(
        "--clause-artifact-dir",
        type=Path,
        default=DEFAULT_CLAUSE_ARTIFACT,
    )
    parser.add_argument(
        "--clause-index-dir",
        type=Path,
        default=DEFAULT_CLAUSE_FAISS,
    )
    parser.add_argument(
        "--bm25-sentence-dir",
        type=Path,
        default=DEFAULT_SENTENCE_BM25,
    )
    parser.add_argument("--search-k", type=int, default=100)
    parser.add_argument("--final-top-k", type=int, default=20)
    parser.add_argument("--rrf-k", type=int, default=60)
    parser.add_argument("--device")
    parser.add_argument("--skip-model", action="store_true")
    parser.add_argument("--skip-retrieval", action="store_true")
    parser.add_argument(
        "--output-prefix",
        type=Path,
        help="不带扩展名的输出前缀",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dataset = load_dataset(args.dataset)

    selected = [
        case
        for case in dataset.cases
        if not args.case_ids
        or case.id in set(args.case_ids)
    ]
    if args.case_ids:
        found = {case.id for case in selected}
        missing = set(args.case_ids) - found
        if missing:
            raise SystemExit(
                "未知 case id: "
                + ", ".join(sorted(missing))
            )
    if not selected:
        raise SystemExit("没有选中任何 Case")

    work_path = args.works.expanduser().resolve()
    print("扫描一次 Work Corpus，解析当前作品 / 目标作品……")
    work_matches = scan_work_matches(
        work_path=work_path,
        cases=selected,
    )

    run = {
        "schema_version": "2",
        "dataset_id": dataset.dataset_id,
        "dataset_version": dataset.dataset_version,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git_sha": git_sha(),
        "config": {
            "search_k": args.search_k,
            "final_top_k": args.final_top_k,
            "rrf_k": args.rrf_k,
            "sentence_artifact_dir": str(args.sentence_artifact_dir),
            "sentence_index_dir": str(args.sentence_index_dir),
            "clause_artifact_dir": str(args.clause_artifact_dir),
            "clause_index_dir": str(args.clause_index_dir),
            "bm25_sentence_dir": str(args.bm25_sentence_dir),
            "works": str(work_path),
            "skip_model": args.skip_model,
            "skip_retrieval": args.skip_retrieval,
        },
        "cases": [],
        "note": (
            "comparison_bucket 只用于快速导航；"
            "最终判断必须人工阅读模型回答与 Retrieval evidence。"
        ),
    }

    for index, case in enumerate(selected, 1):
        print(f"\n[{index}/{len(selected)}] {case.id}")
        match_info = work_matches[case.id]
        chosen_current_work_id = choose_current_work_id(
            case,
            match_info["current"],
        )
        current_work_ids = choose_current_work_ids(
            case,
            match_info["current"],
        )

        item = {
            "case_id": case.id,
            "tier": case.tier,
            "relation": case.relation,
            "rationale": case.rationale,
            "agent_loop_probe": case.agent_loop_probe,
            "retrieval_query": case.retrieval_query,
            "question": case.input.question,
            "target": case.target.model_dump(),
            "work_matches": {
                **match_info,
                "chosen_current_work_id": chosen_current_work_id,
                "excluded_current_work_ids": sorted(current_work_ids),
            },
        }

        standalone_signal: bool | None = None
        tool_signal: bool | None = None
        target_supported_by_tool: bool | None = None
        eligible_rank: int | None = None

        def run_retrieval(
            text: str,
            *,
            include_probe: bool,
        ) -> dict:
            return evaluate_hybrid(
                text=text,
                sentence_artifact_dir=args.sentence_artifact_dir,
                sentence_index_dir=args.sentence_index_dir,
                clause_artifact_dir=args.clause_artifact_dir,
                clause_index_dir=args.clause_index_dir,
                bm25_sentence_dir=args.bm25_sentence_dir,
                work_path=work_path,
                current_work_id=chosen_current_work_id,
                current_work_ids=current_work_ids,
                target_dynasty=case.input.context.dynasty,
                probe_text=(case.target.text if include_probe else None),
                probe_author=(case.target.author if include_probe else None),
                search_k=args.search_k,
                final_top_k=args.final_top_k,
                rrf_k=args.rrf_k,
                device=args.device,
            )

        if not args.skip_model:
            try:
                print("  - ③ 独立 LLM……")
                bare = run_standalone_llm(case)
                item["standalone_llm"] = bare
                standalone_signal = bare["target_signal"]
            except Exception as exc:
                item["standalone_llm_error"] = f"{type(exc).__name__}: {exc}"
                print(f"    失败：{item['standalone_llm_error']}")

            try:
                print("  - ④ 工具增强 LLM……")

                tool_search_audit: dict = {}

                def search_tool(query: str) -> dict:
                    result = run_retrieval(query, include_probe=False)
                    supported, target_rank = tool_target_support(
                        result=result,
                        target_work_ids={
                            item["work_id"]
                            for item in match_info["target"]
                        },
                    )
                    tool_search_audit["target_supported_by_tool"] = supported
                    tool_search_audit["target_rank_in_tool_candidates"] = target_rank
                    return compact_tool_result(result)

                tool_augmented_llm = run_tool_augmented_llm(
                    case,
                    search_tool=search_tool,
                )
                tool_augmented_llm.update(tool_search_audit)
                item["tool_augmented_llm"] = tool_augmented_llm
                tool_signal = tool_augmented_llm["target_signal"]
                target_supported_by_tool = tool_augmented_llm.get(
                    "target_supported_by_tool"
                )
            except Exception as exc:
                item["tool_augmented_llm_error"] = f"{type(exc).__name__}: {exc}"
                print(f"    失败：{item['tool_augmented_llm_error']}")

        if not args.skip_retrieval:
            if not match_info["target"]:
                item["retrieval_error"] = (
                    "Corpus 中没有通过 author + target text "
                    "找到目标 Work；未运行 Hybrid Retrieval"
                )
                print(f"  - Retrieval 跳过：{item['retrieval_error']}")
            else:
                try:
                    print("  - Canonical Hybrid Retrieval 诊断……")
                    result = run_retrieval(
                        case.retrieval_query,
                        include_probe=True,
                    )
                    retrieval = summarize_retrieval(result)
                    item["retrieval"] = retrieval
                    eligible_rank = retrieval["best_eligible_rank"]
                except Exception as exc:
                    item["retrieval_error"] = f"{type(exc).__name__}: {exc}"
                    print(f"    失败：{item['retrieval_error']}")

        item["comparison_bucket"] = comparison_bucket(
            standalone_signal=standalone_signal,
            tool_signal=tool_signal,
            target_supported_by_tool=target_supported_by_tool,
            eligible_rank=eligible_rank,
            agent_loop_probe=case.agent_loop_probe,
        )
        print(
            "  -> "
            f"bare={standalone_signal}, "
            f"tool={tool_signal}, "
            f"target_supported_by_tool={target_supported_by_tool}, "
            f"eligible_rank={eligible_rank}, "
            f"bucket={item['comparison_bucket']}"
        )
        run["cases"].append(item)

    stamp = datetime.now().strftime("%m%d%H%M")
    prefix = (
        args.output_prefix
        if args.output_prefix
        else DEFAULT_REPORT_ROOT / f"retrieval_increment_{stamp}"
    )
    prefix = prefix.expanduser().resolve()
    prefix.parent.mkdir(parents=True, exist_ok=True)

    json_path = prefix.with_suffix(".json")
    md_path = prefix.with_suffix(".md")
    json_path.write_text(
        json.dumps(run, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(
        render_markdown(run),
        encoding="utf-8",
    )

    print(f"\nJSON：{json_path}")
    print(f"Markdown：{md_path}")
    print("把这两个文件直接上传到下一轮对话即可。")


if __name__ == "__main__":
    main()
