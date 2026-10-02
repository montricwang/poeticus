"""Audit all 15 author-collection layouts without normalizing/publishing texts.

This script writes *private local reports* in data/reports/. It does not
resolve glyphs, write curated Poem data, or make quality-accuracy claims.
"""
import argparse
import json
from collections import Counter
from pathlib import Path

from ebooklib import epub

from ..epub.reader import parse_toc
from .coverage import source_block_coverage
from ..extractor.extractor import (
    extract_collection, extract_sections, find_toc_group, toc_file_contexts,
)


# High-impact errors should not be hidden behind hundreds of typography warnings.
PRIORITY_WARNINGS = {
    "missing_inserted_author", "ambiguous_toc_attribution", "empty_body",
    "unresolved_tune_repeat", "unclassified_after_notes",
    "ambiguous_reference_after_verse", "missing_image_src",
    "ambiguous_heading_parts", "unclassified_before_inserted_author",
}


COLLECTIONS = (
    ("温庭筠词集·韦庄词集", "温庭筠", "wen-wei"),
    ("李煜词集（附：李璟词集 冯延巳词集）", "李煜", "nantang"),
    ("柳永词集", "柳永", "liu-yong"),
    ("晏殊词集·晏幾道词集", "晏殊", "yan"),
    ("欧阳修词集", "欧阳修", "ouyang-xiu"),
    ("苏轼词集", "苏轼", "su-shi"),
    ("黄庭坚词集", "黄庭坚", "huang-tingjian"),
    ("秦观词集", "秦观", "qin-guan"),
    ("贺铸词集", "贺铸", "he-zhu"),
    ("周邦彦词集", "周邦彦", "zhou-bangyan"),
    ("李清照词集", "李清照", "li-qingzhao"),
    ("陆游词集", "陆游", "lu-you"),
    ("姜夔词集", "姜夔", "jiang-kui"),
    ("辛弃疾词集", "辛弃疾", "xin-qiji"),
    ("纳兰词集", "纳兰性德", "nalan"),
)


def audit_collection(book, toc, name, author, slug):
    """Capture summary statistics and all warning sites in source order."""
    poems, files = extract_collection(book, toc, name, slug, author)
    nodes = find_toc_group(toc, name)
    contexts = {}
    for filename, owner, zone in toc_file_contexts(nodes or [], name, author):
        value = (owner, zone)
        if filename in contexts and contexts[filename] != value:
            contexts[filename] = ("", "unknown")
        else:
            contexts.setdefault(filename, value)
    sections = [
        section for filename in files
        for section in extract_sections(book, filename, collection=name)
    ]
    if len(poems) != len(sections):
        raise RuntimeError(f"{name}: poem/section order mismatch")
    coverage = source_block_coverage(book, files, sections, name)
    warnings = Counter()
    review = []
    for poem, section in zip(poems, sections):
        structural_blocks = section["blocks"]
        positions = {b["block"]: i for i, b in enumerate(structural_blocks)}
        unknown_shapes = []
        for unknown in section["unknown"]:
            idx = positions.get(unknown["block"])
            if idx is None:
                continue
            def shape(item):
                if item is None:
                    return None
                return {
                    "role": item["role"],
                    "tag": item["tag"],
                    "classes": item["classes"],
                }
            unknown_shapes.append({
                "block": unknown["block"],
                "length": len(unknown["text"]),
                "previous": shape(structural_blocks[idx - 1] if idx else None),
                "current": shape(structural_blocks[idx]),
                "following": shape(structural_blocks[idx + 1]
                                   if idx + 1 < len(structural_blocks) else None),
            })
        for issue in poem.warnings:
            warnings[issue["type"]] += 1
        # Preserve all warning types, without copying every poem's full text.
        if poem.warnings:
            review.append({
                "id": poem.id, "author": poem.author,
                "tune": poem.tune, "title": poem.title,
                "source": {"html": section["html"], "block": section["ordinal"],
                           "anchor": section["anchor"]},
                "zone": section.get("zone_override") or
                        contexts.get(section["html"], (None, "unknown"))[1],
                "warning_types": sorted({i["type"] for i in poem.warnings}),
                "warnings": poem.warnings,
                "unknown_blocks": section["unknown"],
                "preface_lengths": [len(text) for text in poem.content.prefaces],
                "unknown_shapes": unknown_shapes,
                # Structure only; no text from commercially published notes.
                "unsigned_work_structure": [
                    {"role": b["role"], "tag": b["tag"],
                     "classes": b["classes"], "text_length": len(b["text"])}
                    for b in section["blocks"][:8]
                ] if not poem.author else [],
            })
    return {
        "collection": name, "xhtml_count": len(files),
        "source_coverage": coverage,
        "candidate_poems": len(poems), "author_counts": dict(Counter(
            p.author for p in poems
        )), "warning_counts": dict(warnings),
        "missing_tune": sum(p.tune is None for p in poems),
        "unassigned_author": sum(not p.author for p in poems),
        "empty_body": sum(not p.content.text for p in poems),
        "unclassified_work_count": sum(bool(section["unknown"]) for section in sections),
        "unclassified_block_count": sum(len(section["unknown"]) for section in sections),
        "note_marker_in_body": sum(
            any(line.lstrip().startswith(("◆", "◎")) for line in p.content.text)
            for p in poems
        ),
        "review_items": review,
    }


def audit_book(book, toc, only=None):
    selected = [c for c in COLLECTIONS if not only or c[0] == only]
    if not selected:
        raise ValueError(f"Unknown collection: {only}")
    return {"scope": "15 author-collection volumes; unreviewed candidates",
            "results": [audit_collection(book, toc, *c) for c in selected]}


def render_md(report):
    lines = [
        "# EPUB 15 册抽取审计（候选结果，未经文学校勘）", "",
        "| 分册 | XHTML | 候选词作 | 告警涉及作品 | 作者待定 | 空正文 | 正文混入注评标记 | 未追踪源块 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in report["results"]:
        lines.append(
            f'| {item["collection"]} | {item["xhtml_count"]} | '
            f'{item["candidate_poems"]} | {len(item["review_items"])} | '
            f'{item["unassigned_author"]} | {item["empty_body"]} | '
            f'{item["note_marker_in_body"]} | '
            f'{item["source_coverage"]["untracked_blocks"]} |'
        )
    for item in report["results"]:
        lines.extend(["", f'## {item["collection"]}', "",
                      f'作者分布：{item["author_counts"]}', "",
                      f'告警分布：{item["warning_counts"]}', "",
                      f'待分类段落：{item["unclassified_block_count"]} 块，'
                      f'涉及 {item["unclassified_work_count"]} 首候选作品；'
                      '这些段落不会进入 PoemContent，未复核前不允许直接导出。', "",
                      '源块去向：'
                      f'{item["source_coverage"]["total_blocks"]} 块中，'
                      f'{item["source_coverage"]["handled_blocks"]} 块有抽取证据，'
                      f'{item["source_coverage"]["excluded_blocks"]} 块按已知版式排除，'
                      f'{item["source_coverage"]["untracked_blocks"]} 块未追踪。', ""])
        missing = item["source_coverage"]["untracked_sites"]
        if missing:
            lines.append("未追踪源块（仅结构，不含原文；需确认后才允许忽略）：")
            for site in missing[:10]:
                lines.append(
                    f'- `{site["html"]}` 块 {site["block"]} '
                    f'`{site["tag"]}` '
                    f'class=`{",".join(site["classes"]) or "-"}` '
                    f'（{site["text_length"]}字）'
                )
            if len(missing) > 10:
                lines.append(f'- 其余 {len(missing) - 10} 处见本地 JSON')
            lines.append("")
        # Put records likely to affect meaning or authorship first. Keep
        # original source order among records of equal severity.
        ordered_reviews = sorted(
            item["review_items"],
            key=lambda entry: not bool(PRIORITY_WARNINGS & set(entry["warning_types"])),
        )
        for review in ordered_reviews[:12]:
            src = review["source"]
            lines.append(
                f'- `{review["id"]}` {review["author"]} '
                f'{review["tune"] or "?"} / {review["title"] or "无题"}；'
                f'`{src["html"]}` 块 {src["block"]}；'
                f'{", ".join(review["warning_types"])}'
            )
            if ("inserted_author_work" in review["warning_types"]
                    and review.get("preface_lengths")):
                lengths = review["preface_lengths"]
                lines.append(
                    "  - 附词独立题序："
                    + f'{len(lengths)} 段（'
                    + "、".join(f"{length}字" for length in lengths)
                    + "），完整文字只保存在本地提取结果。"
                )
            if review.get("unknown_shapes"):
                shapes = review["unknown_shapes"]
                def label(piece):
                    if piece is None:
                        return "无"
                    return (piece["role"] + "/" + piece["tag"] + "/" +
                            (",".join(piece["classes"]) or "-"))
                lines.append(
                    "  - 待分类块相邻结构（不含原文）："
                    + "; ".join(
                        f'{entry["block"]}: '
                        f'{label(entry["previous"])} → '
                        f'{label(entry["current"])}({entry["length"]}字) → '
                        f'{label(entry["following"])}'
                        for entry in shapes[:3]
                    )
                    + (f'；其余 {len(shapes) - 3} 处见本地 JSON'
                       if len(shapes) > 3 else "")
                )
            if not review["author"]:
                shapes = review.get("unsigned_work_structure", [])
                lines.append(
                    "  - 附词署名未识别；前几个块的结构（不含正文）："
                    + "; ".join(
                        f'{b["role"]}/{b["tag"]}/'
                        f'{",".join(b["classes"]) or "-"}({b["text_length"]}字)'
                        for b in shapes
                    )
                )
        if len(item["review_items"]) > 12:
            lines.append(
                f'- ……另外 {len(item["review_items"]) - 12} 处详见 JSON'
            )
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--epub", type=Path, default=Path(
        "data/raw/历代名家词集精华录.epub"))
    parser.add_argument("--book", help="只审计指定分册；默认 15 册全量")
    parser.add_argument("--output", type=Path, default=Path(
        "data/reports/epub_extraction_audit.md"))
    parser.add_argument("--json-output", type=Path, default=Path(
        "data/reports/epub_extraction_audit.json"))
    args = parser.parse_args()
    book = epub.read_epub(str(args.epub))
    result = audit_book(book, parse_toc(book.toc), args.book)
    for path, content in (
        (args.output, render_md(result)),
        (args.json_output, json.dumps(result, ensure_ascii=False, indent=2))
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    print(f"分册：{len(result['results'])}；报告：{args.output} / {args.json_output}")


if __name__ == "__main__":
    main()
