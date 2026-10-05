"""Create small, repeatable human-review batches for EPUB field classification.

The shareable PLAN contains source positions, predicted roles and questions;
the separate PRIVATE packet contains licensed book excerpts for local review.
Neither is a precision estimate or a substitute for a labelled evaluation set.
"""
import argparse
from pathlib import Path

from ebooklib import epub

from ..epub.reader import parse_toc
from ..extractor.extractor import extract_collection, extract_sections
from ..config import COLLECTIONS
from .inspect_source import inspect_source


KINDS = (
    ("inferred_commentary", "自动续接的评论",
     "这段是否延续前面的 ◆ 评论？是否存在独立引文或新栏目？"),
    ("inferred_annotation", "自动续接的注释",
     "这段是否属于上一条 ◎ 注释，还是另一条内容？"),
    ("inline_style", "正文中的特殊字体",
     "这段特殊字体属于词正文，还是应拆出来的行内注释？"),
    ("clean_complex", "无告警的含注评作品",
     "请核对小序、正文、注释、评论的分界，是否有任何串入或缺失？"),
    ("clean_plain", "无告警的普通作品",
     "请核对词牌、作者、正文起止；这首是否确实没有被遗漏的题序或注评？"),
)
KIND_LABELS = {key: label for key, label, _ in KINDS}
KIND_QUESTIONS = {key: question for key, _, question in KINDS}


def _make_candidate(kind, collection, poem, section, ordinal, role):
    return {
        "kind": kind,
        "collection": collection,
        "poem_id": poem.id,
        "tune": poem.cipai or "未定",
        "html": section["html"],
        "block": ordinal,
        "role": role,
    }


def build_candidates(book, toc, collection_specs=COLLECTIONS):
    """Collect candidate *locations* without retaining source paragraphs.

    This includes both uncertain and apparently successful classifications,
    because success-only warnings cannot measure false positives.
    """
    result = {kind: [] for kind, _, _ in KINDS}
    for collection, author, slug in collection_specs:
        poems, files = extract_collection(book, toc, collection, slug, author)
        sections = [
            section for filename in files
            for section in extract_sections(book, filename, collection=collection)
        ]
        if len(poems) != len(sections):
            raise RuntimeError(f"{collection}: extraction order mismatch")
        for poem, section in zip(poems, sections):
            by_number = {evidence["block"]: evidence["role"]
                         for evidence in section["blocks"]}
            inferred = set()
            for warning in poem.warnings:
                w_type = warning.get("type")
                number = warning.get("block")
                if (not isinstance(number, int)
                        or warning.get("html") != section["html"]
                        or number not in by_number):
                    continue
                kind = None
                if w_type == "inferred_note_continuation":
                    category = warning.get("category")
                    if category == "commentaries":
                        kind = "inferred_commentary"
                    elif category == "annotations":
                        kind = "inferred_annotation"
                elif w_type in (
                    "inline_body_style_review",
                    "inline_note_boundary_review",
                    "inline_note_offset_review",
                ):
                    kind = "inline_style"
                # One sample per warning family per work. Avoid thousands
                # of adjacent continuations in the same scholarly review.
                if kind and kind not in inferred:
                    inferred.add(kind)
                    result[kind].append(_make_candidate(
                        kind, collection, poem, section, number, by_number[number]
                    ))
            if not poem.warnings:
                complex_material = bool(
                    section["prefaces"] or section["annotations"]
                    or section["commentaries"]
                )
                kind = "clean_complex" if complex_material else "clean_plain"
                candidate = _make_candidate(
                    kind, collection, poem, section, section["ordinal"],
                    by_number.get(section["ordinal"], "work_start"),
                )
                if complex_material:
                    # A note near the end of a long poem may be many blocks
                    # away from h2. Show at least one example per category
                    # rather than asking the reviewer to locate it manually.
                    anchors = [section["ordinal"]]
                    for category in (
                        "separate_title", "inserted_preface", "prefaces",
                        "text", "annotations", "commentaries",
                    ):
                        for block in section["blocks"]:
                            if block["role"] == category:
                                if block["block"] not in anchors:
                                    anchors.append(block["block"])
                                break
                    candidate["inspect_blocks"] = anchors
                result[kind].append(candidate)
    return result


def choose_batch(candidates, *, round_number=1, limit=5):
    """Pick an explainable mix of warning patterns and clean controls.

    Selection uses deterministic cycling through available candidates,
    favoring different collections within one batch. It is NOT random
    population sampling, and cannot provide a statistical accuracy estimate.
    """
    if round_number <= 0 or not (1 <= limit <= 20):
        raise ValueError("round_number must be >=1 and limit between 1 and 20")
    chosen = []
    used_books = set()
    used_locations = set()
    counts = {kind: len(pool) for kind, pool in candidates.items()}

    for kind, _, _ in KINDS:
        if len(chosen) >= limit:
            break
        pool = candidates.get(kind, [])
        if not pool:
            continue
        # Round 1 starts at the first source occurrence, later rounds cycle.
        start = ((round_number - 1) * 7) % len(pool)
        rotated = pool[start:] + pool[:start]
        available = [
            item for item in rotated
            if (item["html"], item["block"]) not in used_locations
        ]
        if not available:
            continue
        pick = next(
            (item for item in available if item["collection"] not in used_books),
            available[0],
        )
        entry = dict(pick)
        entry["case_id"] = f"R{round_number:02d}-{len(chosen)+1:02d}"
        chosen.append(entry)
        used_books.add(entry["collection"])
        used_locations.add((entry["html"], entry["block"]))

    return chosen, counts


def plan_markdown(cases, counts, *, round_number=1):
    lines = [
        f"# EPUB 人工分类抽样 · 第 {round_number} 轮",
        "",
        "此文件不含原书正文；仅供安排人工复核。每轮是定点诊断，"
        "**不是分类正确率估计**。",
        "",
        "候选池（按作品去重）："
        + "；".join(f"{KIND_LABELS[k]} {counts.get(k, 0)}"
                   for k, _, _ in KINDS),
        "",
    ]
    if not cases:
        lines.append("没有符合当前抽样类别的样本。")
    for case in cases:
        lines.extend([
            f"## {case['case_id']} · {KIND_LABELS[case['kind']]}",
            "",
            f"**位置：** {case['collection']} / "
            f"{case['poem_id']} / {case['tune']}",
            f"**源块：** `{case['html']}` 块 {case['block']}"
            + (f"；附加检查块 {', '.join(map(str, case['inspect_blocks'][1:]))}"
               if len(case.get("inspect_blocks", [])) > 1 else ""),
            f"**现有分类：** `{case['role']}`",
            f"**请判断：** {KIND_QUESTIONS[case['kind']]}",
            "",
            "- [ ] 分类正确",
            "- [ ] 需要修改（说明应归入什么字段）",
            "- [ ] 仍无法判断",
            "",
        ])
    lines.extend([
        "## 操作提示",
        "",
        "在本地打开对应的私有复核材料；该文件包含每个目标块及前后"
        "文本。如需看原 EPUB 的实际视觉排版，可再打开阅读器。",
        "**私有材料不要上传到公开仓库；若要与 AI 讨论，只需反馈"
        "案例编号、判断和必要的短片段。**",
        "",
    ])
    return "\n".join(lines)


def private_packet_markdown(book, cases):
    lines = [
        "# EPUB 本地人工复核材料（含原书文字，请勿公开）",
        "",
        "根据以下原文片段核实相邻段落在版式和语义上是否确实连续。",
        "",
    ]
    for case in cases:
        lines.extend([
            f"## {case['case_id']} · {case['collection']} · "
            f"{KIND_LABELS[case['kind']]}",
            "",
            f"**问题：** {KIND_QUESTIONS[case['kind']]}",
            "",
            inspect_source(
                book, case["html"],
                case.get("inspect_blocks", [case["block"]]),
                collection=case["collection"],
                before=2 if "inspect_blocks" not in case else 1,
                after=4 if "inspect_blocks" not in case else 2,
                max_chars=240,
            ),
            "",
        ])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--epub", type=Path, default=Path(
        "data/raw/历代名家词集精华录.epub"
    ))
    parser.add_argument("--round", type=int, default=1)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--output", type=Path, default=Path(
        "data/reports/classification_review_plan.md"
    ), help="结构性复核计划（不含书中文字）")
    parser.add_argument("--private-output", type=Path, default=Path(
        "data/reports/classification_review_private.md"
    ), help="本地复核材料（含商业 EPUB 的原文，不可公开）")
    args = parser.parse_args()
    if args.output.resolve() == args.private_output.resolve():
        parser.error("计划与私有材料必须使用不同的路径")
    book = epub.read_epub(str(args.epub))
    toc = parse_toc(book.toc)
    cases, counts = choose_batch(
        build_candidates(book, toc),
        round_number=args.round, limit=args.limit,
    )
    for path, content in (
        (args.output, plan_markdown(cases, counts, round_number=args.round)),
        (args.private_output, private_packet_markdown(book, cases)),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    print(f"生成 {len(cases)} 个待人工复核样本：{args.output}")
    print(f"私有原文材料（切勿上传公开仓库）：{args.private_output}")


if __name__ == "__main__":
    main()
