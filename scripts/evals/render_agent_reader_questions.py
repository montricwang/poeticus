"""Render a reviewable question sheet from the versioned reader benchmark JSON.

No model calls, network requests, or modifications to the question source.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

BANK_PATH = Path(__file__).resolve().parents[2] / "evals" / "agent_reader_100_cases.json"
SHEET_PATH = BANK_PATH.with_name("agent_reader_100_review.md")
LEVELS = (("beginner", "基础"), ("intermediate", "进阶"), ("advanced", "研究"))


def render(bank: dict) -> str:
    counts = Counter(item["level"] for item in bank["cases"])
    split_counts = Counter(item["split"] for item in bank["cases"])
    result = [
        "# Poeticus 综合阅读问答：100 道候选题",
        "",
        "> 2026-10-20 起草。**题目尚未逐条对照原典核验；没有已审定 Gold 答案。** "
        "此表从 [JSON 数据集](agent_reader_100_cases.json) 生成，直接修改 JSON 后重新生成即可。",
        "",
        "本题库从读者提问出发，兼顾普通字词解释、典故、赏析、历代评论、格律、版本校勘和史料研究；"
        "**问题本身不携带预期工具名，也不要求每题调用工具**。部分题可能超出当前可用 API 或语料，"
        "用于发现研究型 Agent 的覆盖缺口。",
        "",
        f"**数量**：基础 {counts['beginner']}；进阶 {counts['intermediate']}；研究 {counts['advanced']}，"
        f"合计 {len(bank['cases'])} 题。"
        f"开发/整理 {split_counts['development']}；暂留复核 {split_counts['reserved_for_review']}。"
        "后者只表示预留，不是经过隔离的正式 held-out。",
        "",
        "**上下文**：有“阅读场景”的题关联 JSON 的作品文本，可能带选区；"
        "无阅读场景的题可独立发问。整首/节选的状态见 JSON 中各 fixture 的 text_scope。"
        "这些文本属于候选转录，仍需独立校核版本。",
        "",
        "## 问题总览",
    ]
    for level, name in LEVELS:
        result.extend(["", f"### {name}（{counts[level]} 题）", "",
                       "| 编号 | 问题 | 阅读场景 | 主题 |",
                       "| --- | --- | --- | --- |"])
        for case in bank["cases"]:
            if case["level"] != level:
                continue
            fixture_id = case["input"].get("fixture_id")
            scene = bank["fixtures"][fixture_id]["title"] if fixture_id else "独立提问"
            question = case["input"]["question"].replace("|", "／")
            result.append(
                f"| {case['id'].split('_')[-1]} | {question} | {scene} | {case['topic']} |"
            )
    result.extend([
        "",
        "## 校核及后续评测边界",
        "",
        "1. **现在只是候选题**：作品正文、术语和争议预设未逐条核验；"
        "先核候选诗文的准确性、底本、题目是否真实可回答，再标记正式状态。",
        "2. **题库与 Gold 分离**：review_focus 是给人审题时看的评估关注点，"
        "不是标准答案、API 路由规则或可以喂给被测 Agent 的 Prompt。",
        "3. **真实评测不强制工具**：比较答案的准确性、适切性、证据来源、"
        "不确定性表达及工具滥用；按真实 Agent Trace 判断究竟调用了什么。",
        "4. **对照实验另行实施**：现有 Agent 与启用 CNKGraph 研究工具的 Agent"
        "统一对照；复用 #344 的词学 Document RAG 金标准时，"
        "仍需分别报告纯检索指标与综合回答质量。",
        "5. **保护题集独立性**：不能在开发过程中把预留组当反复改 Prompt 的训练样本。"
        "正式 held-out 必须经人工审核与实验隔离后再封存。",
        "",
        "更新此表：python -m scripts.evals.render_agent_reader_questions。"
        "数据结构检查：python -m pytest -q tests/evals/test_agent_reader_100_cases.py。",
        "",
    ])
    return "\n".join(result)


def main() -> None:
    bank = json.loads(BANK_PATH.read_text(encoding="utf-8"))
    SHEET_PATH.write_text(render(bank), encoding="utf-8")
    print(f"Rendered {len(bank['cases'])} questions to {SHEET_PATH}")


if __name__ == "__main__":
    main()
