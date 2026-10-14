"""C 实验：当前完整作品被 Eligibility 排除之后，识别尚留在候选里的合集。

只做离线对照，不修改 Poem Retrieval 的生产代码、索引或语料。
所有精确/近似比较直接操作作品的 Unicode 文本，不调用 Embedding。

命令:
    python -m scripts.retrieval.evaluate_self_group_containment
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, Sequence

from backend.data_paths import (
    MODELS_ROOT,
    RETRIEVAL_CORPUS_ROOT,
    RETRIEVAL_REPORTS_ROOT,
    RETRIEVAL_ROOT,
)
from backend.retrieval.poem.serving import RetrievalServingRuntime, ServingCandidate
from backend.retrieval.poem.serving_paths import default_paths
from scripts.retrieval.evaluate_group_candidate_filter import load_selected_work_texts

MatchType = Literal["exact", "normalized", "near", "none"]
DEFAULT_OUTPUT = RETRIEVAL_REPORTS_ROOT / "self_group_containment_experiment.json"
DEFAULT_WORKS = RETRIEVAL_CORPUS_ROOT / "werneror_works.jsonl"


def normalized_letters(text: str) -> str:
    """去掉标点、空格，只保留各语种字母、数字及汉字。"""
    return "".join(character for character in text if character.isalnum())


def min_substring_edit_distance(
    pattern: str,
    text: str,
    *,
    max_edits: int = 2,
) -> int | None:
    """pattern 和 text 任意连续子串的最小 Levenshtein 距离。

    允许替换、插入、删除，text 前后多余内容不计入编辑数。
    简单滚动 DP，O(len(pattern)*len(text))，只用于小规模离线实验。
    """
    if max_edits < 0:
        raise ValueError("max_edits 不能为负数")
    if not pattern:
        raise ValueError("不能对空作品做匹配")
    if len(pattern) > len(text) + max_edits:
        return None
    if pattern in text:
        return 0

    previous = [0] * (len(text) + 1)  # 任意位置可以是子串起点
    for i, character in enumerate(pattern, 1):
        row = [i] + [0] * len(text)
        for j, other in enumerate(text, 1):
            row[j] = min(
                previous[j] + 1,                   # 删除 pattern 中一字
                row[j - 1] + 1,                    # 向 pattern 中插入一字
                previous[j - 1] + (character != other),  # 替换
            )
        previous = row
    best = min(previous)
    return best if best <= max_edits else None


@dataclass(frozen=True)
class Containment:
    method: MatchType
    edits: int | None


def classify_full_work_containment(
    current_text: str,
    candidate_text: str,
    *,
    max_edits: int = 2,
    min_current_chars: int = 24,
    min_extra_chars: int = 24,
) -> Containment:
    """先检查完整作品包含；近似匹配仅作人工复核候选。

    与作者是否相同、当前作品 ID 是否可信分开检查，避免把相似度
    不知不觉升级成作品身份判断。
    """
    current = normalized_letters(current_text)
    candidate = normalized_letters(candidate_text)
    if (
        len(current) < min_current_chars
        or len(candidate) < len(current) + min_extra_chars
    ):
        return Containment("none", None)

    if current_text and current_text in candidate_text:
        return Containment("exact", 0)

    if current in candidate:
        return Containment("normalized", 0)

    if len(current) < 40:  # 短诗允许 2 字误差过于冒险
        return Containment("none", None)

    distance = min_substring_edit_distance(current, candidate, max_edits=max_edits)
    if distance is not None and 1 <= distance <= max_edits:
        return Containment("near", distance)
    return Containment("none", None)


@dataclass(frozen=True)
class FlaggedCandidate:
    rank: int
    work_id: str
    author: str | None
    title: str | None
    method: MatchType
    edits: int | None


def check_remaining_candidates(
    candidates: Sequence[ServingCandidate],
    *,
    current_author: str,
    current_text: str,
    work_texts: dict[str, str],
) -> list[FlaggedCandidate]:
    findings: list[FlaggedCandidate] = []
    for candidate in candidates:
        if candidate.author != current_author:
            continue
        full_text = work_texts.get(candidate.work_id)
        if full_text is None:
            continue
        match = classify_full_work_containment(current_text, full_text)
        if match.method != "none":
            findings.append(
                FlaggedCandidate(
                    rank=candidate.rank,
                    work_id=candidate.work_id,
                    author=candidate.author,
                    title=candidate.title,
                    method=match.method,
                    edits=match.edits,
                )
            )
    return findings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--works", type=Path, default=DEFAULT_WORKS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    # 直接从 Corpus 中选定可信的独立作品 ID；不由标题猜测身份。
    probes = [
        ("陆游-轻鸥", "werneror_poetry:宋_2.csv:13653", "陆游", "宋", "片片轻鸥落晚沙"),
        ("陆游-酒如", "werneror_poetry:宋_2.csv:13653", "陆游", "宋", "酒如清露鲊如花"),
        ("晏殊-破阵子", "werneror_poetry:宋_2.csv:57473", "晏殊", "宋", "燕子来时新社"),
        ("杜牧-赠别", "werneror_poetry:唐.csv:27912", "杜牧", "唐", "蜡烛有心还惜别"),
    ]
    current_works = load_selected_work_texts(
        args.works, {work_id for _, work_id, _, _, _ in probes}
    )
    runtime = RetrievalServingRuntime(
        default_paths(RETRIEVAL_ROOT, MODELS_ROOT), device=args.device, search_k=100
    )

    searches = []
    for name, work_id, author, dynasty, query in probes:
        current_text = current_works[work_id]
        result = runtime.search(
            query, current_text=current_text, current_author=author,
            target_dynasty=dynasty, final_top_k=16,
        )
        searches.append((name, work_id, author, query, current_text, result))

    wanted = {c.work_id for _, _, _, _, _, result in searches for c in result.candidates}
    texts = load_selected_work_texts(args.works, wanted)

    cases: list[dict[str, object]] = []
    for name, work_id, author, query, current_text, result in searches:
        flagged = check_remaining_candidates(
            result.candidates, current_author=author,
            current_text=current_text, work_texts=texts,
        )
        # 只在模拟「当前 ID 确实被精确识别」时列出可进一步考虑排除的
        # 字符串完全/去标点包含结果；模糊包含永不自动进入此集合。
        trusted_current = work_id in result.current_work_aliases
        exact_candidates = {
            match.work_id for match in flagged
            if match.method in ("exact", "normalized")
        } if trusted_current else set()
        baseline = result.candidates[:8]
        after = tuple(
            c for c in result.candidates if c.work_id not in exact_candidates
        )[:8]
        cases.append({
            "case": name, "query": query, "current_work_id": work_id,
            "current_chars": len(current_text),
            "current_alias_recognized": trusted_current,
            "baseline": [
                {"rank": c.rank, "title": c.title, "author": c.author, "work_id": c.work_id}
                for c in baseline
            ],
            "flagged": [asdict(c) for c in flagged],
            "suppressed_in_counterfactual": sorted(exact_candidates),
            "counterfactual": [
                {"rank": i, "title": c.title, "author": c.author, "work_id": c.work_id}
                for i, c in enumerate(after, 1)
            ],
        })
        print(
            name, "trusted", trusted_current,
            "flags", [(x.rank, x.title, x.method, x.edits) for x in flagged],
            flush=True,
        )

    source = current_works[probes[0][1]]
    variant = source.replace("落晚沙", "下晚沙", 1)
    double_variant = variant.replace("青门", "朱门", 1)
    punctuation_variant = "".join(ch for ch in source if ch.isalnum())
    seven_poem_text = texts.get("werneror_poetry:宋_4.csv:51342")
    if seven_poem_text is None:
        extra = load_selected_work_texts(
            args.works, {"werneror_poetry:宋_4.csv:51342"}
        )
        seven_poem_text = extra["werneror_poetry:宋_4.csv:51342"]
    variants = {
        "original": source,
        "punctuation_removed": punctuation_variant,
        "one_changed_char": variant,
        "two_changed_chars": double_variant,
        "four_changed_chars": source.replace("懒向", "欲往").replace("青门", "朱门").replace("落晚沙", "下晚沙"),
    }
    variant_results = {
        name: asdict(classify_full_work_containment(text, seven_poem_text))
        for name, text in variants.items()
    }
    print("LuYou synthetic variants:", variant_results, flush=True)

    output = {
        "rule": "compare full current Work with full remaining candidate Work; no new embeddings",
        "candidates": cases,
        "synthetic_variants": variant_results,
        "limitations": [
            "Exact containment does not prove that a longer same-author work is a literary collection.",
            "Near match is diagnostic only; it is never used for automatic suppression.",
            "Only trusted current work IDs are eligible for exact-match counterfactual suppression.",
            "The experiment reads full candidate text from existing corpus JSONL offline, not via online SQL.",
            "No production Serving, index, metadata schema or corpus records were modified.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("Report:", args.output)


if __name__ == "__main__":
    main()
