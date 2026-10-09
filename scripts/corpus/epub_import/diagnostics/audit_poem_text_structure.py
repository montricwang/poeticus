#!/usr/bin/env python3
"""只读审计各分册 Poeticus 中间 JSON 的 content.text 结构。

Default input: poeticus-data/reading-corpus/normalized/all_normalized.json (private, not present in GitHub).
Produces a metadata-only report and a SEPARATE, private literary-text review file
under poeticus-data/reports/epub-import/ (gitignored by Poeticus). Does not change source JSON.

This tool describes structures, NOT literary correctness. In particular, an array
entry is not necessarily a ci stanza (片), or a sentence (句).
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import TypedDict

from backend.data_paths import EPUB_REPORTS_ROOT, READING_NORMALIZED_ROOT
from statistics import median

# 这些只是供人工复核的候选信号，不代表已经确认文本有误。
MARKERS = {
    "explicit_gap": re.compile(r"以下缺|以下闕|以下阙|下[片闋阕]缺|上[片闋阕]缺|原缺|缺[一二三四五六七八九十\d]+字"),
    "missing_character_box": re.compile(r"[□◻◯]{1,}|\uFFFD"),
    "unresolved_glyph": re.compile(r"\{\{glyph:[^}]*\}\}"),
    "ideograph_description": re.compile(r"[\u2ff0-\u2fff]"),
}
END_PUNCTUATION = re.compile(r"[，,。.!！?？；;：:、…）】」』]+[\s\u3000]*$")
class AuditInfo(TypedDict):
    """One work's structural evidence, not a literary classification."""

    parts: list[str]
    number: int
    nonempty: int
    lengths: list[int]
    median_length: int | float
    max_length: int
    blank_positions: list[int]
    edge_or_double_blank: bool
    embedded_newline_elements: int
    embedded_newline_boundaries: int
    punct_newline_boundaries: int
    nonpunct_newline_boundaries: int
    empty_inner_lines: int
    has_cr: bool
    short_units: bool
    marker_types: list[str]
    inline_note_count: int
    inline_note_issues: list[str]
    note_warning_types: list[str]
    warning_types: list[str]


type AuditEntry = tuple[dict[str, object], AuditInfo]
type SampleEntry = tuple[dict[str, object], AuditInfo, str]


NOTE_WARNING_NAMES = {
    "inline_body_style_review", "inline_author_note",
    "inline_author_note_candidate", "inline_editorial_gap",
}


def md_cell(value: object) -> str:
    return str(value).replace("|", "／").replace("\n", " ")


def segments_for(record: dict[str, object]) -> list[str]:
    content = record.get("content")
    if not isinstance(content, dict):
        raise ValueError("content 不是对象")
    parts = content.get("text")
    if not isinstance(parts, list) or not all(isinstance(x, str) for x in parts):
        raise ValueError("content.text 不是字符串数组")
    return [part for part in parts if isinstance(part, str)]


def examine(record: dict[str, object]) -> AuditInfo:
    parts = segments_for(record)
    content = record["content"]
    assert isinstance(content, dict)
    nonempty = [s for s in parts if s.strip()]
    blanks = [i for i, s in enumerate(parts) if not s.strip()]
    lengths = [len(s.strip()) for s in nonempty]
    embedded_lines = [s.split("\n") for s in nonempty if "\n" in s]
    boundaries = [line for lines in embedded_lines for line in lines[:-1]]
    punct_boundary = sum(bool(END_PUNCTUATION.search(line)) for line in boundaries)
    empty_inner_lines = sum(not line.strip() for lines in embedded_lines for line in lines[1:-1])
    punctuation_ended = sum(bool(END_PUNCTUATION.search(s)) for s in nonempty)
    note_records = content.get("inline_notes", [])
    note_issues = []
    if not isinstance(note_records, list):
        note_issues.append("inline_notes_not_list")
        note_records = []
    for pos, note in enumerate(note_records):
        if not isinstance(note, dict):
            note_issues.append(f"note_{pos}_not_object")
            continue
        i, start, end, text = [note.get(k) for k in ("paragraph_index", "start", "end", "text")]
        if (not isinstance(i, int) or isinstance(i, bool) or i < 0 or i >= len(parts)
                or not isinstance(start, int) or isinstance(start, bool)
                or not isinstance(end, int) or isinstance(end, bool)
                or not isinstance(text, str)):
            note_issues.append(f"note_{pos}_invalid_position")
        elif not (0 <= start < end <= len(parts[i]) and parts[i][start:end] == text):
            note_issues.append(f"note_{pos}_offset_mismatch")
    warnings = record.get("warnings", [])
    if not isinstance(warnings, list):
        warnings = []
    warning_types = {kind for w in warnings if isinstance(w, dict) if isinstance((kind := w.get("type")), str)}
    body = "\n".join(nonempty)
    marker_types = sorted(k for k, p in MARKERS.items() if p.search(body))
    edge_blank = bool(blanks) and (blanks[0] == 0 or blanks[-1] == len(parts)-1)
    adjacent_blank = any(b == a+1 for a, b in zip(blanks, blanks[1:]))
    trailing_ratio = (punctuation_ended / len(nonempty)) if nonempty else 0
    # 这里只是诊断启发式，不把它当作语义句法或分片分类器。
    short_units = len(nonempty) >= 5 and median(lengths) <= 20 and trailing_ratio >= 0.7
    return {
        "parts": parts,
        "number": len(parts),
        "nonempty": len(nonempty),
        "lengths": lengths,
        "median_length": median(lengths) if lengths else 0,
        "max_length": max(lengths, default=0),
        "blank_positions": blanks,
        "edge_or_double_blank": edge_blank or adjacent_blank,
        "embedded_newline_elements": len(embedded_lines),
        "embedded_newline_boundaries": len(boundaries),
        "punct_newline_boundaries": punct_boundary,
        "nonpunct_newline_boundaries": len(boundaries)-punct_boundary,
        "empty_inner_lines": empty_inner_lines,
        "has_cr": any("\r" in s for s in parts),
        "short_units": short_units,
        "marker_types": marker_types,
        "inline_note_count": len(note_records),
        "inline_note_issues": note_issues,
        "note_warning_types": sorted(warning_types & NOTE_WARNING_NAMES),
        "warning_types": sorted(warning_types),
    }


def label(info: AuditInfo) -> str:
    n = info["nonempty"]
    if not n:
        return "0 个非空元素"
    if n == 1:
        return "1 个非空元素"
    if n == 2:
        return "2 个非空元素"
    if n <= 4:
        return "3–4 个非空元素"
    return "5 个以上非空元素"


def pick_samples(entries: list[AuditEntry], limit: int) -> list[SampleEntry]:
    """优先展示有对比价值的样本，而不是连续倾倒作品。"""
    if not limit:
        return []
    selected: list[SampleEntry] = []
    seen: set[str] = set()
    def select(predicate, reason, count=1):
        for work, info in entries:
            identity = str(work.get("id", ""))
            if identity in seen or not predicate(work, info):
                continue
            selected.append((work, info, reason))
            seen.add(identity)
            if len(selected) >= limit or count == 1:
                return
            count -= 1
    # 优先覆盖用户明确提出的三个假设。
    for reason, test in [
        ("李清照：空元素", lambda p, i: "李清照" in str(p.get("collection")) and bool(i["blank_positions"])),
        ("李清照：无空元素", lambda p, i: "李清照" in str(p.get("collection")) and not i["blank_positions"]),
        ("南唐合刊：元素内换行且在标点处", lambda p, i: "李煜" in str(p.get("collection")) and i["punct_newline_boundaries"] > 0),
        ("南唐合刊：元素内换行且在非标点处", lambda p, i: "李煜" in str(p.get("collection")) and i["nonpunct_newline_boundaries"] > 0),
        ("行内自注坐标", lambda p, i: i["inline_note_count"] > 0),
        ("自注疑点 warning", lambda p, i: bool(i["note_warning_types"])),
        ("缺文/未解字样", lambda p, i: bool(i["marker_types"])),
        ("较多正文元素", lambda p, i: i["nonempty"] >= 5),
        ("单个较长元素", lambda p, i: i["max_length"] >= 160),
    ]:
        if len(selected) >= limit:
            break
        select(test, reason)
    # 条件允许时尽量让 15 个来源分册都能进入样本。
    coll = list(dict.fromkeys(str(p.get("collection", "（未知）")) for p, _ in entries))
    for name in coll:
        if len(selected) >= limit:
            break
        select(lambda p, i, n=name: str(p.get("collection", "（未知）")) == n,
               "按来源抽样")
    return selected


def aggregate(entries: list[AuditEntry]):
    groups = defaultdict(list)
    author_groups = defaultdict(list)
    for p, info in entries:
        group = str(p.get("collection") or "（缺少词集）")
        groups[group].append((p, info))
        author_groups[(group, str(p.get("author") or "（作者不明）"))].append((p, info))
    return groups, author_groups


def make_report(entries: list[AuditEntry], errors: list[str], source_name: str,
                *, example_limit: int = 12) -> str:
    groups, authors = aggregate(entries)
    out = [
        "# 作品正文结构审计（仅元数据，不含词文）", "",
        f"- 输入：`{md_cell(source_name)}`（本地私人数据）",
        f"- 正常读取作品：{len(entries)}；结构异常记录：{len(errors)}；来源分册：{len(groups)}", 
        "- 审计范围：`content.text` 的数组元素、空元素、内部换行、长度、缺文候选标记、行内自注坐标与相关 warning。",
        "- 注意：元素数量不等于上下片数量，句末标点不等于可靠断句；脚本不会修改任何 JSON。", "",
        "## 1. 分册结构矩阵", "",
        "| 词集 | 作品 | 1 元素 | 2 元素 | 3–4 元素 | ≥5 元素 | 有空段 | 有内部换行 | 短元素候选 | 行内自注 | 缺文/字形候选 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, items in groups.items():
        c = Counter(label(info) for _, info in items)
        out.append("| " + md_cell(name) + " | " + " | ".join(map(str,[
            len(items), c["1 个非空元素"], c["2 个非空元素"], c["3–4 个非空元素"],
            c["5 个以上非空元素"], sum(bool(i["blank_positions"]) for _, i in items),
            sum(bool(i["embedded_newline_elements"]) for _, i in items),
            sum(i["short_units"] for _, i in items),
            sum(bool(i["inline_note_count"]) for _, i in items),
            sum(bool(i["marker_types"]) for _, i in items),
        ])) + " |")
    out.extend(["", "## 2. 作者粒度（合刊不能直接当作某位词人）", "",
                "| 分册 / 作者 | 作品 | 有内部换行 | 有空段 | ≥5 非空元素 | 自注位置记录 |",
                "| --- | ---: | ---: | ---: | ---: | ---: |"])
    for (col, author), items in authors.items():
        out.append("| " + md_cell(f"{col} / {author}") + " | " + " | ".join(map(str,[
            len(items), sum(bool(i["embedded_newline_elements"]) for _, i in items),
            sum(bool(i["blank_positions"]) for _, i in items),
            sum(i["nonempty"] >= 5 for _, i in items),
            sum(bool(i["inline_note_count"]) for _, i in items),
        ])) + " |")
    out.extend(["", "## 3. 行内换行到底发生在何处？", "",
                "分辨 `\\n` 前是句末标点还是其他字。非标点不一定错误（例如换页），但不应自动删除或插入空格。", "",
                "| 词集 | 含换行作品 | 换行边界数 | 标点后 | 非标点后 | 元素内部空白行 |",
                "| --- | ---: | ---: | ---: | ---: | ---: |"])
    for name, items in groups.items():
        out.append("| " + md_cell(name) + " | " + " | ".join(map(str,[
            sum(bool(i["embedded_newline_elements"]) for _, i in items),
            sum(i["embedded_newline_boundaries"] for _, i in items),
            sum(i["punct_newline_boundaries"] for _, i in items),
            sum(i["nonpunct_newline_boundaries"] for _, i in items),
            sum(i["empty_inner_lines"] for _, i in items),
        ])) + " |")
    flags = [
        ("边缘或连续空元素", lambda x: x["edge_or_double_blank"]),
        ("元素内有 CR 回车", lambda x: x["has_cr"]),
        ("非标点后内部换行", lambda x: x["nonpunct_newline_boundaries"] > 0),
        ("正文短元素较多（句级候选）", lambda x: x["short_units"]),
        ("元素长度至少 160 字", lambda x: x["max_length"] >= 160),
        ("存在行内自注记录", lambda x: x["inline_note_count"] > 0),
        ("行内自注坐标异常", lambda x: bool(x["inline_note_issues"])),
        ("存在自注相关告警", lambda x: bool(x["note_warning_types"])),
    ] + [(f"正文候选标记：{key}", lambda x, k=key: k in x["marker_types"]) for key in MARKERS]
    out.extend(["", "## 4. 需要观察的结构与候选问题", "",
                "以下是规则筛出的**待核实候选**，不是自动断言文本有错。每项只列前几个作品 ID。", ""])
    for name, cond in flags:
        matched = [str(p.get("id", "（无 ID）")) for p, i in entries if cond(i)]
        out.append(f"- **{name}**：{len(matched)} 首；样本 ID：" +
                   (", ".join(f"`{md_cell(x)}`" for x in matched[:example_limit]) if matched else "无"))
    out.extend(["", "## 5. 初步判断（待本地原文抽样核实）", "",
                "- 单元素 / 双元素作品与短元素密集作品分开观察，不能直接断言前者按片、后者按句。",
                "- 只有源头实际存在的空元素、内部换行可以被识别为排版证据；不推断它们必然代表片界。",
                "- 若要合并 / 切分数组，应先决定如何重定位 `inline_notes.paragraph_index/start/end`。",
                "- 缺文、IDS、方框与未解析图片字表示不同问题，不能统一替换成空白。",
                "- 来源顺序和正文片段顺序应原样保留，任何展示转换须可复核，不能覆盖中间源数据。",
                "- 合刊请看本报告作者粒度统计，不能把全卷特征直接归于卷首作者。", ""])
    if errors:
        out.extend(["## 数据结构错误", ""])
        out.extend(f"- {md_cell(error)}" for error in errors[:50])
    return "\n".join(out) + "\n"


def make_private_samples(sample: list[SampleEntry]) -> str:
    lines = ["# 正文结构抽样（含私人词文，请勿提交或公开分享）", "",
             "原样显示 `content.text` 的每个元素及内部换行；本报告仅用于人工判断是否需要调整呈现。", ""]
    for work, info, reason in sample:
        work_id = str(work.get("id", "?"))
        lines.extend([f"## {work_id} · {str(work.get('author') or '作者未明')} · {str(work.get('tune') or '词牌未明')}", "",
                      f"- 选中原因：{reason}",
                      f"- 分册：{work.get('collection')}",
                      f"- 原数组元素：{info['number']}；非空：{info['nonempty']}；空元素下标（从 1 起）：{[i+1 for i in info['blank_positions']]}",
                      f"- 元素内换行边界：{info['embedded_newline_boundaries']}（标点后 {info['punct_newline_boundaries']}，非标点后 {info['nonpunct_newline_boundaries']}）",
                      f"- 缺文／字形候选：{', '.join(info['marker_types']) or '无'}；行内自注记录数：{info['inline_note_count']}", "",
                      "### 原数组（序号对应原始 paragraph_index）", ""])
        for j, part in enumerate(info["parts"]):
            lines.extend([f"**元素 {j}**（长度 {len(part)}）", "", "```text", part if part else "〔空字符串〕", "```", ""])
        if info["inline_note_count"]:
            # 为保护隐私并提高调试效率，只记录位置，不重复注释正文。
            content = work.get("content")
            notes = content.get("inline_notes", []) if isinstance(content, dict) else []
            for note in notes if isinstance(notes, list) else []:
                if isinstance(note, dict):
                    lines.append(f"- 自注位置：元素 {note.get('paragraph_index')}，字符区间 [{note.get('start')}, {note.get('end')})")
            lines.append("")
    return "\n".join(lines) + "\n"


def self_test() -> None:
    def rec(parts, *, notes=None, warnings=None):
        return {"id": "synthetic", "collection": "测试分册", "author": "测试人",
                "content": {"text": parts, "inline_notes": notes or []}, "warnings": warnings or []}
    a = examine(rec(["甲，", "乙。", "", "丙，", "丁。", "戊。"]))
    assert a["nonempty"] == 5 and a["blank_positions"] == [2] and a["short_units"]
    b = examine(rec(["甲，\n乙。", "丙\n丁。", "□", "（以下缺）"]))
    assert (b["embedded_newline_boundaries"], b["punct_newline_boundaries"],
            b["nonpunct_newline_boundaries"]) == (2, 1, 1)
    assert set(b["marker_types"]) == {"explicit_gap", "missing_character_box"}
    c = examine(rec(["甲乙丙"], notes=[{"paragraph_index":0,"start":1,"end":2,"text":"乙"}]))
    assert c["inline_note_count"] == 1 and not c["inline_note_issues"]
    d = examine(rec(["甲乙丙"], notes=[{"paragraph_index":0,"start":1,"end":2,"text":"甲"}]))
    assert d["inline_note_issues"] == ["note_0_offset_mismatch"]
    e = examine(rec(["甲\n\n乙", "\r丙", "⿰缶吾", "{{glyph:fake.png}}", "", ""] ))
    assert e["empty_inner_lines"] == 1 and e["edge_or_double_blank"] and e["has_cr"]
    assert set(e["marker_types"]) == {"unresolved_glyph", "ideograph_description"}
    report = make_report([(rec(["甲乙。"]), examine(rec(["甲乙。"])))], [], "synthetic.json")
    assert "词集" in report and "正文结构审计" in report
    assert len(pick_samples([(rec(["甲乙。"]), examine(rec(["甲乙。"])))], 1)) == 1
    print("SELF-TEST PASS: 空段 / 换行边界 / 标记 / 自注坐标 / 汇总 / 抽样（合成数据）")


def main() -> None:
    parser = argparse.ArgumentParser(description="全库 content.text 结构画像；默认只读私人中间 JSON")
    parser.add_argument("--input", default=str(READING_NORMALIZED_ROOT / "all_normalized.json"), help="私有规范化中间作品数组")
    parser.add_argument("--report-dir", default=str(EPUB_REPORTS_ROOT), help="本地私人报告目录（默认受 .gitignore 保护）")
    parser.add_argument("--preview-count", type=int, default=24, help="原文私有抽样上限，0 表示不创建私有预览")
    parser.add_argument("--self-test", action="store_true", help="仅运行合成测试，不接触真实数据")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if not (0 <= args.preview_count <= 60):
        parser.error("--preview-count 只能在 0 到 60 之间")
    source = Path(args.input)
    if not source.is_file():
        parser.error(f"未找到 {source}；请先在自己的电脑上执行 EPUB --all 导出")
    items = json.loads(source.read_text(encoding="utf-8-sig"))
    if not isinstance(items, list):
        parser.error("JSON 顶层必须为作品数组")
    entries: list[AuditEntry] = []
    errors: list[str] = []
    for n, record in enumerate(items, 1):
        if not isinstance(record, dict):
            errors.append(f"序号 {n}: 不是作品对象")
            continue
        try:
            info = examine(record)
            entries.append((record, info))
        except ValueError as exc:
            errors.append(f"序号 {n} / ID {record.get('id', '未知')}: {exc}")
    dest = Path(args.report_dir)
    dest.mkdir(parents=True, exist_ok=True)
    stat_file = dest / "content_structure_audit.md"
    stat_file.write_text(make_report(entries, errors, source.name), encoding="utf-8")
    print(f"已检查 {len(items)} 条作品；正文结构有效 {len(entries)}，错误 {len(errors)}。")
    print(f"元数据统计（不含原文）：{stat_file}")
    if args.preview_count:
        sample = pick_samples(entries, args.preview_count)
        private_file = dest / "content_structure_samples_PRIVATE.md"
        private_file.write_text(make_private_samples(sample), encoding="utf-8")
        print(f"含原文的私人样本：{private_file}（{len(sample)} 首；请勿上传 GitHub）")
    print("没有修改任何输入 JSON。")


if __name__ == "__main__":
    main()
