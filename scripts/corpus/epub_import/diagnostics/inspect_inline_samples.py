"""挑选真实带样式的行内词句 span，供本地视觉与语义复核。

The plan is structure-only. The optional private packet contains published
text/XHTML; keep it in gitignored data/reports/ and never commit it.
"""
import argparse
from collections import defaultdict
from pathlib import Path

from ebooklib import epub

from ..epub.reader import parse_toc
from .audit_inline_styles import collect_inline_evidence
from .inspect_source import inspect_source


# 这里只保存人工核对过的来源坐标，不保存受版权保护的正文。
# 包含最初两个案例和用户后来补充的十个案例。
REVIEWED_FONT1_SITES = frozenset({
    ("text00214.html", 679), ("text00278.html", 135),
    ("text00214.html", 696), ("text00278.html", 519),
    ("text00280.html", 87), ("text00281.html", 754),
    ("text00214.html", 755), ("text00278.html", 520),
    ("text00279.html", 12), ("text00279.html", 188),
    ("text00279.html", 243), ("text00279.html", 424),
})


def _group_key(signature):
    """返回样式类族，而不是外层 p 的 class。"""
    if signature.startswith("span class="):
        return signature.split(" style=", 1)[0].removeprefix("span class=")
    return signature


def select_inline_samples(audit, *, families=("kaiti", "font1"),
                          per_style=3, remaining=False):
    """先保证每个分册一个样本，再在剩余位置中分散抽样。"""
    if per_style < 1 or per_style > 15:
        raise ValueError("per_style must be between 1 and 15")
    groups = defaultdict(list)
    for site in audit["sites"]:
        if not site["warned"]:
            continue
        for signature in site["style_signatures"]:
            family = _group_key(signature)
            if family not in families:
                continue
            if (remaining and family == "font1"
                    and (site["html"], site["block"]) in REVIEWED_FONT1_SITES):
                continue
            groups[family].append(site)

    picks = []
    for family in families:
        pool = groups.get(family, [])
        collections = {}
        for site in pool:
            collections.setdefault(site["collection"], []).append(site)
        selected = []
        seen = set()

        def include(site):
            key = (site["collection"], site["html"], site["block"])
            if key in seen:
                return
            selected.append(site)
            seen.add(key)

        # 这个样式涉及的每个分册都至少保留一个样本。
        for subset in collections.values():
            if len(selected) >= per_style:
                break
            include(subset[0])
        # 剩余样本沿来源顺序分散，避免集中在相邻位置。
        if len(selected) < per_style and pool:
            for site in (pool[len(pool) // 2], pool[-1], *pool):
                if len(selected) >= per_style:
                    break
                include(site)
        for idx, site in enumerate(selected, 1):
            picks.append({
                "case_id": f"{family}-{idx:02d}",
                "family": family,
                "collection": site["collection"],
                "html": site["html"],
                "block": site["block"],
                "paragraph_classes": site["paragraph_classes"],
                "styled_spans": site["styled_spans"],
                "has_gap_marker": site["has_gap_marker"],
            })
    return picks


def render_plan(picks):
    lines = [
        "# EPUB 行内样式定点复核计划（无原文）",
        "",
        "先核实特殊字体是否是小字说明、校勘标记、原有词句或其他用途；"
        "**不要仅凭字体 class 直接把整类内容从词正文删除。**",
        "",
        "| 编号 | 样式 | 分册 | XHTML | 块号 | 残缺标记 |",
        "|---|---|---|---|---:|---|",
    ]
    for case in picks:
        lines.append(
            f"| {case['case_id']} | \`{case['family']}\` | "
            f"{case['collection']} | \`{case['html']}\` | "
            f"{case['block']} | "
            f"{'有' if case['has_gap_marker'] else '无'} |"
        )
    if not picks:
        lines.append("| （没有找到候选） | — | — | — | — | — |")
    lines.extend([
        "",
        "具体原文、内嵌 span 和前后段落，请查看本地 private packet；"
        "只需按编号讨论类型或提供少量必要短片段。",
        "",
    ])
    return "\n".join(lines)


def render_private_packet(book, picks):
    lines = [
        "# EPUB 行内样式私人复核材料（含原文，切勿公开）",
        "",
        "请观察目标 span 包住的文字，以及它和相邻词句的关系。",
        "",
    ]
    for case in picks:
        lines.extend([
            f"## {case['case_id']} · {case['collection']}",
            "",
            f"**类别：** {case['family']}；**目标：** "
            f"\`{case['html']}\` 块 {case['block']}",
            "",
            inspect_source(
                book, case["html"], [case["block"]],
                collection=case["collection"],
                before=1, after=1, max_chars=200, show_html=True,
            ),
            "",
        ])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--epub", type=Path, default=Path(
        "data/raw/历代名家词集精华录.epub"
    ))
    parser.add_argument("--style", choices=("kaiti", "font1"),
                        action="append", help="仅抽取指定的 span class；可重复")
    parser.add_argument("--per-style", type=int, default=3)
    parser.add_argument("--remaining", action="store_true",
                        help="跳过此前已人工核对的 font1 位置，只看剩余样本")
    parser.add_argument("--output", type=Path, default=Path(
        "data/reports/inline_style_review_plan.md"
    ))
    parser.add_argument("--private-output", type=Path, default=Path(
        "data/reports/inline_style_review_private.md"
    ))
    args = parser.parse_args()
    if args.output.resolve() == args.private_output.resolve():
        parser.error("结构报告与原文报告必须分开存储")
    book = epub.read_epub(str(args.epub))
    audit = collect_inline_evidence(book, parse_toc(book.toc))
    cases = select_inline_samples(
        audit, families=tuple(dict.fromkeys(args.style or ("kaiti", "font1"))),
        per_style=args.per_style, remaining=args.remaining,
    )
    for path, report in (
        (args.output, render_plan(cases)),
        (args.private_output, render_private_packet(book, cases)),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(report, encoding="utf-8")
    print(f"已选 {len(cases)} 个样本（无原文）：{args.output}")
    print(f"原始 XHTML 及词句的本地私有材料：{args.private_output}")


if __name__ == "__main__":
    main()
