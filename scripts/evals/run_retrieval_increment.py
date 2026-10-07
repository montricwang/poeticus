"""Compare base-model memory with local full-corpus Retrieval.

This is the first small increment-value eval, not a final RAG benchmark.

For each fixed case it records:
1. control_no_tools: current product model / prompt, tool access disabled;
2. hybrid_retrieval: Dense sentence + Dense clause + sentence BM25
   -> Work-level RRF -> Candidate Eligibility;
3. a lightweight navigation heuristic, never a Ground Truth score.

The script writes detailed JSON plus a readable Markdown report so large
results can be uploaded directly instead of copied through chat.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from evals.schema import EvalInput
from scripts.retrieval.exact_search import DEFAULT_DATA_ROOT, DEFAULT_WORKS
from scripts.retrieval.hybrid_eval import evaluate_hybrid
from scripts.retrieval.lexical_bm25 import DEFAULT_INDEX_ROOT


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = ROOT / "evals" / "retrieval_increment_cases.json"
DEFAULT_REPORT_ROOT = ROOT / "data" / "reports"

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


def run_control_no_tools(case: RetrievalIncrementCase) -> dict:
    """Run the product model / prompt with tool use disabled."""
    # Lazy imports keep --skip-model usable without LLM_API_KEY.
    from backend.ai.context import PoemContext
    from backend.ai.graph import TOOLS, _agent_user_message
    from backend.ai.model import client
    from backend.ai.prompt_loader import compose_prompt
    from backend.config import LLM_MAX_OUTPUT_TOKENS, LLM_MODEL

    context = PoemContext(
        id=f"retrieval-increment:{case.id}",
        title=case.input.context.title,
        author=case.input.context.author,
        dynasty=case.input.context.dynasty,
    )
    state = {
        "poem": case.input.poem,
        "question": case.input.question,
        "selection": case.input.selection,
        "context": context,
        "history": [
            message.model_dump()
            for message in case.input.history
        ],
    }

    messages = [
        {
            "role": "system",
            "content": compose_prompt(
                "agent_decide",
                "output_style",
            ),
        }
    ]
    messages.extend(state["history"])
    messages.append(
        {
            "role": "user",
            "content": _agent_user_message(state),
        }
    )

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

    answer = response.choices[0].message.content
    anchor_hits = [
        anchor
        for anchor in case.target.answer_anchors
        if anchor in answer
    ]
    author_hit = case.target.author in answer

    return {
        "model": LLM_MODEL,
        "answer": answer,
        "target_author_mentioned": author_hit,
        "target_anchor_hits": anchor_hits,
        "target_signal": author_hit and bool(anchor_hits),
    }


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


def heuristic_bucket(
    *,
    base_signal: bool | None,
    eligible_rank: int | None,
) -> str:
    """Navigation label only; never a quality score."""
    retrieval_top5 = (
        eligible_rank is not None
        and eligible_rank <= 5
    )
    retrieval_top20 = (
        eligible_rank is not None
        and eligible_rank <= 20
    )

    if base_signal is True and retrieval_top5:
        return "both_strong"
    if base_signal is True and not retrieval_top20:
        return "base_model_stronger"
    if base_signal is False and retrieval_top5:
        return "retrieval_increment_candidate"
    if base_signal is False and retrieval_top20:
        return "retrieval_possible_increment"
    if base_signal is False:
        return "both_gap"
    return "partial_run"


def _md_escape(value: object) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def render_markdown(run: dict) -> str:
    lines = [
        "# Retrieval Increment Eval",
        "",
        "> 第一轮只比较裸模型参数记忆与本地 Retrieval 候选发现。",
        "> 这不是最终 RAG 总分，也不自动判断文学关系真伪。",
        "",
        "## Summary",
        "",
        "| Case | 档位 | 裸模型目标信号 | Retrieval eligible rank | Top-5 | 导航标签 |",
        "| --- | --- | --- | ---: | --- | --- |",
    ]

    for item in run["cases"]:
        base = item.get("control_no_tools")
        retrieval = item.get("retrieval")
        base_signal = (
            None
            if not isinstance(base, dict)
            else base.get("target_signal")
        )
        rank = (
            None
            if not isinstance(retrieval, dict)
            else retrieval.get("best_eligible_rank")
        )
        top5 = isinstance(rank, int) and rank <= 5
        lines.append(
            "| "
            + " | ".join(
                [
                    _md_escape(item["case_id"]),
                    _md_escape(item["tier"]),
                    _md_escape(base_signal),
                    _md_escape(rank),
                    _md_escape(top5),
                    _md_escape(item["heuristic_bucket"]),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## How to read",
            "",
            "- target_signal 只是作者名 + 目标特征短语的字符串命中，用于快速导航，不是自动判对错。",
            "- Retrieval rank 是现有 Hybrid + RRF + Eligibility 下的 Work 排名，不等于文学关系概率。",
            "- known_control / mid_distance / long_tail_probe 是本轮抽样角色，不是严格难度等级。",
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
                f"- Query: {item['retrieval_query']}",
                (
                    "- Expected target: "
                    f"{item['target']['author']} — "
                    f"{item['target']['text']}"
                ),
                f"- Heuristic bucket: {item['heuristic_bucket']}",
                (
                    "- Current Work matches: "
                    f"{len(item['work_matches']['current'])}; "
                    "chosen: "
                    f"{item['work_matches']['chosen_current_work_id']}"
                ),
                (
                    "- Target Work matches: "
                    f"{len(item['work_matches']['target'])}"
                ),
                "",
            ]
        )

        base = item.get("control_no_tools")
        if isinstance(base, dict):
            lines.extend(
                [
                    "### 裸模型",
                    "",
                    (
                        "- target_author_mentioned: "
                        f"{base.get('target_author_mentioned')}"
                    ),
                    (
                        "- target_anchor_hits: "
                        f"{base.get('target_anchor_hits')}"
                    ),
                    "",
                    base.get("answer", ""),
                    "",
                ]
            )
        elif item.get("control_error"):
            lines.extend(
                [
                    "### 裸模型",
                    "",
                    f"运行失败：{item['control_error']}",
                    "",
                ]
            )

        retrieval = item.get("retrieval")
        if isinstance(retrieval, dict):
            lines.extend(
                [
                    "### Retrieval",
                    "",
                    (
                        "- best_fused_rank: "
                        f"{retrieval.get('best_fused_rank')}"
                    ),
                    (
                        "- best_eligible_rank: "
                        f"{retrieval.get('best_eligible_rank')}"
                    ),
                    (
                        "- target_in_top5: "
                        f"{retrieval.get('target_in_top5')}"
                    ),
                    "",
                    "| rank | author | title | best evidence | support_count |",
                    "| ---: | --- | --- | --- | ---: |",
                ]
            )
            for candidate in retrieval.get("top_candidates") or []:
                evidence = candidate.get("best_evidence") or {}
                evidence_text = (
                    f"{evidence.get('channel')} "
                    f"#{evidence.get('rank')}: "
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

            lines.extend(["", "#### Target supports", ""])
            probes = retrieval.get("probes") or []
            if not probes:
                lines.append("没有 target probe 结果。")
            for probe in probes:
                lines.append(
                    f"- {probe.get('work_id')}: "
                    f"fused={probe.get('fused_rank')}, "
                    f"eligible={probe.get('eligible_rank')}"
                )
                for support in probe.get("list_supports") or []:
                    lines.append(
                        "  - "
                        f"{support.get('channel')} / "
                        f"{support.get('query')} -> rank "
                        f"{support.get('rank')}: "
                        f"{support.get('text')}"
                    )
            lines.append("")
        elif item.get("retrieval_error"):
            lines.extend(
                [
                    "### Retrieval",
                    "",
                    f"运行失败：{item['retrieval_error']}",
                    "",
                ]
            )

    return "\n".join(lines).rstrip() + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="比较裸模型与本地 Hybrid Retrieval 的增量价值"
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
        "schema_version": "1",
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
            "heuristic_bucket 只用于快速导航；"
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

        item = {
            "case_id": case.id,
            "tier": case.tier,
            "relation": case.relation,
            "rationale": case.rationale,
            "retrieval_query": case.retrieval_query,
            "question": case.input.question,
            "target": case.target.model_dump(),
            "work_matches": {
                **match_info,
                "chosen_current_work_id": chosen_current_work_id,
            },
        }

        base_signal: bool | None = None
        if not args.skip_model:
            try:
                print("  - 裸模型……")
                control = run_control_no_tools(case)
                item["control_no_tools"] = control
                base_signal = control["target_signal"]
            except Exception as exc:
                item["control_error"] = (
                    f"{type(exc).__name__}: {exc}"
                )
                print(f"    失败：{item['control_error']}")

        eligible_rank: int | None = None
        if not args.skip_retrieval:
            if not match_info["target"]:
                item["retrieval_error"] = (
                    "Corpus 中没有通过 author + target text "
                    "找到目标 Work；未运行 Hybrid Retrieval"
                )
                print(f"  - Retrieval 跳过：{item['retrieval_error']}")
            else:
                try:
                    print("  - Hybrid Retrieval……")
                    result = evaluate_hybrid(
                        text=case.retrieval_query,
                        sentence_artifact_dir=args.sentence_artifact_dir,
                        sentence_index_dir=args.sentence_index_dir,
                        clause_artifact_dir=args.clause_artifact_dir,
                        clause_index_dir=args.clause_index_dir,
                        bm25_sentence_dir=args.bm25_sentence_dir,
                        work_path=work_path,
                        current_work_id=chosen_current_work_id,
                        target_dynasty=case.input.context.dynasty,
                        probe_text=case.target.text,
                        probe_author=case.target.author,
                        search_k=args.search_k,
                        final_top_k=args.final_top_k,
                        rrf_k=args.rrf_k,
                        device=args.device,
                    )
                    retrieval = summarize_retrieval(result)
                    item["retrieval"] = retrieval
                    eligible_rank = retrieval[
                        "best_eligible_rank"
                    ]
                except Exception as exc:
                    item["retrieval_error"] = (
                        f"{type(exc).__name__}: {exc}"
                    )
                    print(f"    失败：{item['retrieval_error']}")

        item["heuristic_bucket"] = heuristic_bucket(
            base_signal=base_signal,
            eligible_rank=eligible_rank,
        )
        print(
            "  -> "
            f"base_signal={base_signal}, "
            f"eligible_rank={eligible_rank}, "
            f"bucket={item['heuristic_bucket']}"
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
