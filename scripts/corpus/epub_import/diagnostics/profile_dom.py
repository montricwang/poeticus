"""Profile TOC-linked EPUB XHTML/typography before designing extraction rules.

Outputs aggregate templates and bounded examples; NEVER writes the full source text.
DOM and CSS patterns are evidence, not automatic tune/title/preface labels.
"""

import argparse
import json
import re
import warnings
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import unquote

from bs4 import (
    BeautifulSoup,
    Comment,
    Declaration,
    Doctype,
    ProcessingInstruction,
    Tag,
    XMLParsedAsHTMLWarning,
)
from bs4.element import NavigableString
from ebooklib import epub

from ..epub.css import StyleResolver
from ..epub.reader import parse_toc

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

EPUB_PATH = Path("data/raw/历代名家词集精华录.epub")
MD_PATH = Path("data/reports/epub_dom_layout_profile.md")
JSON_PATH = Path("data/reports/epub_dom_layout_profile.json")
HEADINGS = {f"h{i}" for i in range(1, 7)}
YEAR_PATTERN = re.compile(r"[（(]\d{4}[）)]$")
SAMPLE_LIMIT = 4  # 高频模板展示数量
RARE_THRESHOLD = 10  # 低频模板保留全部实例
PAGE_SAMPLE_LIMIT = 15  # 每分册最多抽取的 XHTML 文件数
WINDOW_SAMPLE_LIMIT = 18  # 每分册最多展示的连续片段总数
BLOCK_SAMPLE_LIMIT = 10  # 每段连续窗口展示的块数
TRANSITION_SAMPLE_LIMIT = 4  # 每分册抽取的“符号→无符号”相邻案例
STYLE_KEYS = ("font-family", "font-size", "font-weight", "font-style", "color")
INLINE_TAGS = {
    "span",
    "small",
    "big",
    "strong",
    "b",
    "em",
    "i",
    "font",
    "ruby",
    "rt",
    "a",
    "br",
    "img",
    "sup",
    "sub",
}


def gather_links(node):
    if node.get("href"):
        yield node["href"]
    for child in node.get("children", []):
        yield from gather_links(child)


def volume_files(volume):
    """File -> top-level TOC groups; each XHTML is analyzed only once per volume."""
    found = defaultdict(set)
    for group in volume.get("children", []):
        for href in gather_links(group):
            name = unquote(href.split("#", 1)[0])
            if name.lower().endswith((".html", ".xhtml")):
                found[name].add(group["title"])
    if volume.get("href"):
        name = unquote(volume["href"].split("#", 1)[0])
        if name.lower().endswith((".html", ".xhtml")):
            found[name].add("分册")
    return {key: sorted(values) for key, values in found.items()}


def css_class(tag):
    return ".".join(tag.get("class", [])) or "(none)"


def node_label(tag):
    return f"{tag.name}.{css_class(tag)}" if tag.get("class") else tag.name


def compact(text, limit=85):
    text = " ".join(text.split())
    return text[:limit] + ("…" if len(text) > limit else "")


def typography(style):
    return {k: style[k] for k in STYLE_KEYS if k in style}


def content_runs(heading, styles):
    """Preserve each text run's nearest styled element, not get_text() flattening."""
    runs = []
    for node in heading.descendants:
        if isinstance(node, NavigableString):
            value = str(node).strip()
            if not value:
                continue
            owner = node.parent
            style = styles.style(owner)
            runs.append(
                {
                    "text": compact(value, 110),
                    "element": node_label(owner),
                    "style": typography(style),
                    "style_sources": {
                        k: styles.provenance(owner).get(k)
                        for k in STYLE_KEYS
                        if k in style
                    },
                }
            )
        elif isinstance(node, Tag) and node.name == "br":
            runs.append(
                {"text": "↵", "element": "br", "style": {}, "style_sources": {}}
            )
        elif isinstance(node, Tag) and node.name == "img":
            runs.append(
                {
                    "text": f"[img:{node.get('src', '')}]",
                    "element": "img",
                    "style": {},
                    "style_sources": {},
                }
            )
    return runs


def heading_template(heading, runs, styles):
    """Structural and typographic signature, independent of title wording."""
    root_style = typography(styles.style(heading))
    run_signatures = []
    for run in runs:
        signature = (run["element"], tuple(sorted(run["style"].items())))
        if not run_signatures or run_signatures[-1] != signature:
            run_signatures.append(signature)
    shape = {
        "root": node_label(heading),
        "root_style": root_style,
        "runs": [{"element": x[0], "style": dict(x[1])} for x in run_signatures],
    }
    return json.dumps(shape, ensure_ascii=False, sort_keys=True), shape


def paragraph_feature(tag, text):
    if not text:
        return "纯图片" if tag.find("img") else "空段落"
    if text.startswith("◎"):
        return "◎开头"
    if text.startswith("◆"):
        return "◆开头"
    if len(text) <= 50 and YEAR_PATTERN.search(text):
        return "短句+四位年份"
    return "其他文字"


def add_example(record, example):
    """低频模板保留每一次出现；高频模板只保存有上限的候选样本。"""
    samples = record["samples"]
    if len(samples) < RARE_THRESHOLD:
        samples.append(example)
    elif example.get("title", "").startswith("又") and not any(
        x.get("title", "").startswith("又") for x in samples
    ):
        samples[-1] = example


def display_examples(record):
    """出现不超过 10 次的模板全列出（同名且重复出现也不去重）。"""
    samples = record["samples"]
    if record["count"] <= RARE_THRESHOLD:
        return samples
    chosen = [samples[i] for i in spread_indices(len(samples), SAMPLE_LIMIT)]
    # “又”之类同名承前标题需要保留一个明显实例。
    special = next((x for x in samples if x.get("title", "").startswith("又")), None)
    if special is not None and special not in chosen:
        chosen[-1] = special
    return chosen


def spread_indices(length, limit):
    """确定性的首／中／尾等距抽样，不受运行顺序及随机数影响。"""
    if length <= 0:
        return []
    count = min(length, limit)
    if count == 1:
        return [0]
    return [round(i * (length - 1) / (count - 1)) for i in range(count)]


def selected_templates(records, top_n=10):
    """高频前若干种 + 所有低频种类，防止异常版式被 Top-N 截掉。"""
    top = records[:top_n]
    return top + [rec for rec in records[top_n:] if rec["count"] <= RARE_THRESHOLD]


def unhandled_text(soup):
    """Detect text not nested in p or headings, which the existing parser might miss."""
    grouped = Counter()
    samples = {}
    for text in soup.find_all(string=True):
        if (
            not isinstance(text, NavigableString)
            or isinstance(text, (Comment, Declaration, Doctype, ProcessingInstruction))
            or not text.strip()
        ):
            continue
        if text.parent.find_parent(["p", *sorted(HEADINGS)]):
            continue
        if text.parent.name in HEADINGS | {"p", "script", "style", "title"}:
            continue
        if text.parent.find_parent(["script", "style", "head"]):
            continue
        name = text.parent.name
        grouped[name] += 1
        samples.setdefault(name, compact(str(text)))
    return grouped, samples


def document_soup(book, html_name):
    item = book.get_item_with_href(html_name)
    if item is None:
        return None
    raw = getattr(item, "content", None)
    if raw is None:
        raw = item.get_content()
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8-sig")
    return BeautifulSoup(raw, "lxml")


def document_blocks(soup):
    """阅读顺序中的原子块，排除包裹其他块的 div，避免重复正文。"""
    wanted = [*sorted(HEADINGS), "p", "div"]
    return [
        tag
        for tag in soup.find_all(wanted)
        if tag.name != "div" or tag.find(wanted) is None
    ]


def block_summary(element, styles):
    """结构、文本、样式证据；不赋予词牌/正文/评论等语义。"""
    data = {
        "tag": node_label(element),
        "text": compact(element.get_text(" ", strip=True), 115),
        "style": typography(styles.style(element)),
    }
    # 标题必须展示文字片段与其各自的 CSS；段落仅在存在混合样式时展开。
    runs = content_runs(element, styles)
    significant = element.name in HEADINGS or any(
        run["element"] not in (node_label(element), "br") or run["element"] == "br"
        for run in runs
    )
    if significant:
        data["runs"] = runs[:8]
        if len(runs) > 8:
            data["runs_truncated"] = len(runs) - 8
    return data


def window_sample(blocks, start, count, styles, label):
    end = min(start + count, len(blocks))
    return {
        "position": label,
        "block_range": [start + 1, end],
        "total_blocks": len(blocks),
        "blocks": [block_summary(x, styles) for x in blocks[start:end]],
    }


def align_to_heading(blocks, index):
    """中/末位置优先从附近标题开始，避免把一首作品劈成不相干的半段。"""
    lower = max(0, index - 8)
    for pos in range(index, lower - 1, -1):
        if blocks[pos].name in HEADINGS:
            return pos
    return index


def sample_document_layout(book, html_name, resolver):
    """同一 XHTML 内按首、中、末抽取连续块，不只看文件开头。"""
    soup = document_soup(book, html_name)
    if soup is None:
        return None
    styles = resolver.for_document(soup, html_name)
    blocks = document_blocks(soup)
    if not blocks:
        return None

    total = len(blocks)
    starts = [(0, "开头")]
    if total > BLOCK_SAMPLE_LIMIT * 2:
        starts.append((align_to_heading(blocks, total // 2), "中间"))
    if total > BLOCK_SAMPLE_LIMIT * 4:
        starts.append(
            (align_to_heading(blocks, max(0, total - BLOCK_SAMPLE_LIMIT)), "末尾")
        )

    windows = []
    visited = set()
    for start, label in starts:
        if start in visited:
            continue
        visited.add(start)
        windows.append(window_sample(blocks, start, BLOCK_SAMPLE_LIMIT, styles, label))
    return {"html": html_name, "windows": windows}


def sample_marker_transition(book, html_name, block_index, resolver):
    """截取带符号段落紧接无符号段落的实际上下文；不推断它们的关系。"""
    soup = document_soup(book, html_name)
    if soup is None:
        return None
    styles = resolver.for_document(soup, html_name)
    blocks = soup.find_all(["p", *sorted(HEADINGS)])
    if block_index >= len(blocks):
        return None
    start = max(0, block_index - 3)
    end = min(len(blocks), block_index + 7)
    return {
        "html": html_name,
        "position": "◆/◎→无标记段落（仅是结构相邻）",
        "block_range": [start + 1, end],
        "total_blocks": len(blocks),
        "blocks": [block_summary(x, styles) for x in blocks[start:end]],
    }


def inspect_document(
    book, html_name, groups, resolver, templates, paragraphs, coverage
):
    soup = document_soup(book, html_name)
    if soup is None:
        coverage["missing"].append(html_name)
        return
    styles = resolver.for_document(soup, html_name)
    coverage["files"] += 1
    coverage["linked_css"].update(styles.paths)

    headings = soup.find_all(list(HEADINGS))
    blocks = soup.find_all(["p", *sorted(HEADINGS)])
    coverage["heading_tags"].update(h.name for h in headings)
    heading_seen = False
    for idx, element in enumerate(blocks):
        if element.name in HEADINGS:
            if element.name == "h2":
                heading_seen = True
            runs = content_runs(element, styles)
            key, signature = heading_template(element, runs, styles)
            record = templates.setdefault(
                key,
                {"signature": signature, "count": 0, "groups": set(), "samples": []},
            )
            record["count"] += 1
            record["groups"].update(groups)
            add_example(
                record,
                {
                    "html": html_name,
                    "title": compact(element.get_text(" ", strip=True), 130),
                    "id": element.get("id"),
                    "block_index": idx + 1,
                    "runs": runs,
                },
            )
            continue
        text = element.get_text(" ", strip=True)
        feature = paragraph_feature(element, text)
        nested = Counter(
            t.name
            for t in element.descendants
            if isinstance(t, Tag) and t.name in INLINE_TAGS
        )
        style = typography(styles.style(element))
        signature = {"element": node_label(element), "feature": feature, "style": style}
        key = json.dumps(signature, ensure_ascii=False, sort_keys=True)
        record = paragraphs.setdefault(
            key,
            {
                "signature": signature,
                "count": 0,
                "groups": set(),
                "before_first_h2": 0,
                "after_heading": 0,
                "before_heading": 0,
                "inline_tags": Counter(),
                "samples": [],
            },
        )
        record["count"] += 1
        record["groups"].update(groups)
        record["inline_tags"].update(nested)
        if not heading_seen:
            record["before_first_h2"] += 1
        if idx > 0 and blocks[idx - 1].name in HEADINGS:
            record["after_heading"] += 1
        if idx + 1 < len(blocks) and blocks[idx + 1].name in HEADINGS:
            record["before_heading"] += 1
        add_example(
            record,
            {
                "html": html_name,
                "block_index": idx + 1,
                "title": compact(text),
                "inline_tags": dict(nested),
            },
        )
        # 只收集位置供后续定量抽样；不当成评论续段的自动结论。
        if (
            text.startswith(("◆", "◎"))
            and idx + 1 < len(blocks)
            and blocks[idx + 1].name == "p"
            and not blocks[idx + 1].get_text(" ", strip=True).startswith(("◆", "◎"))
            and html_name not in coverage["transition_files"]
        ):
            coverage["transition_files"].add(html_name)
            coverage["transition_candidates"].append((html_name, idx))

    stray, examples = unhandled_text(soup)
    coverage["unhandled_tags"].update(stray)
    for name, sample in examples.items():
        coverage["unhandled_samples"].setdefault(
            name, {"html": html_name, "text": sample}
        )


def finish(records):
    output = []
    for record in sorted(
        records.values(), key=lambda r: (-r["count"], str(r["signature"]))
    ):
        item = dict(record)
        item["groups"] = sorted(record["groups"])
        if "inline_tags" in item:
            item["inline_tags"] = dict(record["inline_tags"].most_common())
        output.append(item)
    return output


def profile_volume(book, volume, resolver):
    templates, paragraphs = {}, {}
    coverage = {
        "files": 0,
        "missing": [],
        "linked_css": set(),
        "heading_tags": Counter(),
        "unhandled_tags": Counter(),
        "unhandled_samples": {},
        "transition_candidates": [],
        "transition_files": set(),
    }
    files = volume_files(volume)
    names = list(files)
    for html_name, groups in files.items():
        inspect_document(
            book, html_name, groups, resolver, templates, paragraphs, coverage
        )

    # 先扫描所有 XHTML；再跨全册均匀选文档，避免大型分册只观察前十五页。
    candidates_by_file = []
    for index in spread_indices(len(names), PAGE_SAMPLE_LIMIT):
        sample = sample_document_layout(book, names[index], resolver)
        if sample:
            candidates_by_file.append(sample)

    # 先确保跨文件覆盖，然后按余下预算补充长文件的内部窗口。
    layout_samples = [
        {"html": x["html"], "windows": [x["windows"][0]]} for x in candidates_by_file
    ]
    budget = WINDOW_SAMPLE_LIMIT - len(layout_samples)
    # 首先补长文件的末尾，再补中间，优先展现可能出现的后半部特殊结构。
    for position in ("末尾", "中间"):
        for source, target in zip(candidates_by_file, layout_samples):
            if budget <= 0:
                break
            matched = next(
                (w for w in source["windows"][1:] if w["position"] == position), None
            )
            if matched:
                target["windows"].append(matched)
                budget -= 1
    for sample in layout_samples:
        sample["windows"].sort(key=lambda w: w["block_range"][0])

    # 从全部 XHTML 收集的相邻结构中挑选，避免局部采样碰巧漏掉续段。
    candidates = coverage["transition_candidates"]
    transitions = []
    for index in spread_indices(len(candidates), TRANSITION_SAMPLE_LIMIT):
        html_name, block_index = candidates[index]
        sample = sample_marker_transition(book, html_name, block_index, resolver)
        if sample:
            transitions.append(sample)

    return {
        "volume": volume["title"],
        "toc_files": len(files),
        "analyzed_files": coverage["files"],
        "missing_files": coverage["missing"],
        "linked_css": sorted(coverage["linked_css"]),
        "heading_tags": dict(coverage["heading_tags"]),
        "heading_templates": finish(templates),
        "paragraph_templates": finish(paragraphs),
        "other_text_tags": dict(coverage["unhandled_tags"].most_common()),
        "other_text_samples": coverage["unhandled_samples"],
        "layout_samples": layout_samples,
        "marker_transitions": transitions,
        "marker_transition_files": len(candidates),
    }


def escape_md(s):
    return str(s).replace("|", "\\|").replace("\n", " ").replace("`", "'")


def short_style(style):
    return ", ".join(f"{k}={v}" for k, v in style.items()) or "(未声明)"


def run_description(run):
    """把同一 heading 下各个 text/span/br 的差异直接展示给 AI。"""
    if run["element"] == "br":
        return "`<br>` ↵（显式换行）"
    return (
        f"`{escape_md(run['element'])}`「{escape_md(run['text'])}」"
        f"〔{escape_md(short_style(run['style']))}〕"
    )


def render_block(block):
    msg = f"`{escape_md(block['tag'])}` {escape_md(block['text'])}"
    if block["style"]:
        msg += f" 〔{escape_md(short_style(block['style']))}〕"
    return msg


def render_window(lines, window):
    a, b = window["block_range"]
    lines.append(
        f"**{escape_md(window['position'])}**（块 {a}–{b} / {window['total_blocks']}）"
    )
    for block in window["blocks"]:
        lines.append(f"- {render_block(block)}")
        # 标题一定展开；普通段落仅展示内嵌样式，且限制片段数量。
        if block.get("runs"):
            unique = {
                (r["element"], tuple(sorted(r["style"].items()))) for r in block["runs"]
            }
            if block["tag"].split(".")[0] in HEADINGS or len(unique) > 1:
                for run in block["runs"]:
                    lines.append(f"  - {run_description(run)}")
                if block.get("runs_truncated"):
                    lines.append(
                        f"  - ……其余 {block['runs_truncated']} 个内部片段未展示"
                    )
    lines.append("")


def render_md(report):
    lines = [
        "# EPUB DOM 与 CSS 排版画像",
        "",
        "统计范围：全部 TOC 关联 XHTML；每个文件在同一分册只扫描一次。",
        "这是排版证据，不自动把标签判定为词牌、词题、正文、小序或评论。",
        "CSS 字体/字号为静态级联近似结果；`em` 等相对单位未换算成浏览器最终像素值。",
        "低频模板（出现 ≤10 次）列出所有实例；高频模板只列有限实例。",
        "连续片段展示相邻块，`◆/◎→无标记` 不等于已确认存在续段。",
        "",
        "## 总览",
        "",
        "| 分册 | XHTML | 标题模板 | 段落模板 | CSS |",
        "|---|---:|---:|---:|---:|",
    ]
    for v in report["volumes"]:
        lines.append(
            f"| {escape_md(v['volume'])} | {v['analyzed_files']} | "
            f"{len(v['heading_templates'])} | {len(v['paragraph_templates'])} | "
            f"{len(v['linked_css'])} |"
        )

    for v in report["volumes"]:
        lines.extend(
            [
                "",
                f"## {escape_md(v['volume'])}",
                "",
                f"XHTML：{v['analyzed_files']} / 目录关联 {v['toc_files']}；"
                f"样式表：{', '.join(map(escape_md, v['linked_css'])) or '无'}；"
                f"标题标签：{escape_md(v['heading_tags'])}。",
                "",
                "### 标题 DOM 模板及内部字体差异",
                "",
            ]
        )
        headings = selected_templates(v["heading_templates"])
        for n, rec in enumerate(headings, 1):
            sig = rec["signature"]
            lines.append(
                f"**H{n}** `{escape_md(sig['root'])}` ×{rec['count']}；"
                f"根样式：{escape_md(short_style(sig['root_style']))}。"
            )
            for sample in display_examples(rec):
                lines.append(
                    f"- `{escape_md(sample['html'])}` 块 {sample.get('block_index', '?')}："
                    f"{escape_md(sample['title'])}"
                )
                for run in sample.get("runs", []):
                    lines.append(f"  - {run_description(run)}")
            lines.append("")

        lines.extend(["### 段落模板", ""])
        for n, rec in enumerate(selected_templates(v["paragraph_templates"]), 1):
            sig = rec["signature"]
            lines.append(
                f"**P{n}** `{escape_md(sig['element'])}` ×{rec['count']}；"
                f"特征：{escape_md(sig['feature'])}；"
                f"样式：{escape_md(short_style(sig['style']))}。"
            )
            for sample in display_examples(rec):
                lines.append(
                    f"- `{escape_md(sample['html'])}` 块 {sample.get('block_index', '?')}："
                    f"{escape_md(sample['title'])}"
                )
            lines.append("")

        lines.extend(
            [
                "### 连续结构抽样",
                "",
                "文件按首／中／尾分布抽取；长文件也在内部抽取中、末段。",
                "",
            ]
        )
        for sample in v.get("layout_samples", []):
            lines.append(f"#### `{escape_md(sample['html'])}`")
            lines.append("")
            for window in sample["windows"]:
                render_window(lines, window)

        lines.extend(
            [
                "### 符号与无标记段落相邻的样例",
                "",
                f"本册检测到 {v.get('marker_transition_files', 0)} 个 XHTML 含此类相邻结构；下面只展示有限的连续证据。",
                "",
            ]
        )
        for sample in v.get("marker_transitions", []):
            lines.append(f"#### `{escape_md(sample['html'])}`")
            lines.append("")
            render_window(lines, sample)

        if v["other_text_tags"]:
            lines.extend(["### 非段落、非标题标签中的文字（待核对）", ""])
            for tag, count in v["other_text_tags"].items():
                example = v["other_text_samples"].get(tag, {})
                lines.append(
                    f"- `{escape_md(tag)}` ×{count}；"
                    f"`{escape_md(example.get('html', '?'))}`：{escape_md(example.get('text', ''))}"
                )
            lines.append("")
        if v["missing_files"]:
            lines.append(
                "未找到的 XHTML：" + "、".join(map(escape_md, v["missing_files"]))
            )

    if report.get("css_warnings"):
        lines.extend(["## 静态 CSS 无法完整解释的情况", ""])
        for warning in report["css_warnings"]:
            lines.append(f"- {escape_md(warning)}")
    return "\n".join(lines) + "\n"


def render_overview_md(report):
    """面向 AI 的短报告；逐条证据与低频模板全例见分册报告。"""
    lines = [
        "# EPUB DOM 与 CSS 排版画像：总览",
        "",
        "这是面向 AI 的压缩导读，依据全量 DOM/CSS 扫描；不自动判断文学语义。",
        "完整的标题文字分段、低频模板全部实例、分层连续窗口和异常相邻案例，见同目录的分册报告。",
        "CSS `em`/`%` 等值保留原始相对单位，未换算浏览器最终像素值。",
        "",
        "| 分册 | XHTML | 标题模板 | 段落模板 | 相邻过渡文件 |",
        "|---|---:|---:|---:|---:|",
    ]
    for v in report["volumes"]:
        lines.append(
            f"| {escape_md(v['volume'])} | {v['analyzed_files']} | "
            f"{len(v['heading_templates'])} | {len(v['paragraph_templates'])} | "
            f"{v.get('marker_transition_files', 0)} |"
        )

    for v in report["volumes"]:
        lines.extend(["", f"## {escape_md(v['volume'])}", ""])
        lines.append(
            f"XHTML {v['analyzed_files']}；标题分布 {escape_md(v['heading_tags'])}；"
            f"CSS {len(v['linked_css'])} 份。"
        )

        # 一个高频代表 + 一个内部样式有差异的标题，避免仅看纯文本。
        heading_records = v["heading_templates"]
        chosen = heading_records[:1]
        different = next(
            (
                rec
                for rec in heading_records
                if any(
                    len(
                        {
                            (r["element"], tuple(sorted(r["style"].items())))
                            for r in ex.get("runs", [])
                        }
                    )
                    > 1
                    for ex in rec["samples"]
                )
            ),
            None,
        )
        if different is not None and different not in chosen:
            chosen.append(different)
        for rec in chosen:
            ex = next(
                (x for x in rec["samples"] if len(x.get("runs", [])) > 1),
                rec["samples"][0] if rec["samples"] else None,
            )
            if ex is None:
                continue
            lines.append(
                f"- 标题 `{escape_md(rec['signature']['root'])}` ×{rec['count']}："
                f"{escape_md(ex['title'])}"
            )
            for run in ex.get("runs", [])[:5]:
                lines.append(f"  - {run_description(run)}")

        for rec in v["paragraph_templates"][:5]:
            sig = rec["signature"]
            example = rec["samples"][0]["title"] if rec["samples"] else ""
            lines.append(
                f"- 段落 `{escape_md(sig['element'])}` ×{rec['count']} "
                f"({escape_md(sig['feature'])})：{escape_md(compact(example, 60))}"
            )
        rare_h = sum(rec["count"] <= RARE_THRESHOLD for rec in v["heading_templates"])
        rare_p = sum(rec["count"] <= RARE_THRESHOLD for rec in v["paragraph_templates"])
        lines.append(
            f"- 低频模板：标题 {rare_h} 种、段落 {rare_p} 种（全部实例见分册报告）。"
        )

        # 尽量选能看见 h2 的作品内容窗口，而非只显示版权页/目录页。
        windows = [
            (sample["html"], window)
            for sample in v.get("layout_samples", [])
            for window in sample["windows"]
        ]
        selected = next(
            (
                x
                for x in windows
                if any(block["tag"].split(".")[0] == "h2" for block in x[1]["blocks"])
            ),
            windows[0] if windows else None,
        )
        if selected:
            html_name, window = selected
            a, b = window["block_range"]
            lines.append(
                f"- 连续片段：`{escape_md(html_name)}` 块 {a}–{b}（节选前 6 块）："
            )
            for block in window["blocks"][:6]:
                lines.append(
                    f"  - `{escape_md(block['tag'])}` {escape_md(compact(block['text'], 75))}"
                )

        if v.get("marker_transitions"):
            trans = v["marker_transitions"][0]
            target = next(
                (
                    i
                    for i, blk in enumerate(trans["blocks"])
                    if blk["text"].startswith(("◆", "◎"))
                ),
                0,
            )
            lines.append(f"- 符号→无标记段落例：`{escape_md(trans['html'])}`")
            for blk in trans["blocks"][target : target + 3]:
                lines.append(
                    f"  - `{escape_md(blk['tag'])}` {escape_md(compact(blk['text'], 75))}"
                )

    if report.get("css_warnings"):
        lines.append("")
        lines.append(
            f"静态 CSS 未完全解释的情况：{len(report['css_warnings'])} 条，需结合分册报告复核。"
        )
    return "\n".join(lines) + "\n"


def volume_report_filename(index, name):
    """对 Windows 非法文件名字符做清理，保留可读的中文分册名。"""
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    return f"{index:02d}_{safe[:70] or 'volume'}.md"


def run(book, toc, book_filter=None):
    resolver = StyleResolver(book)
    volumes = [
        node
        for node in toc
        if node["title"] != "总目录"
        and (book_filter is None or node["title"] == book_filter)
    ]
    if not volumes:
        raise ValueError(f"未找到分册：{book_filter}")
    report = {
        "schema_version": 2,
        "scope": "DOM/CSS structural evidence; not a literary semantic classification",
        "volumes": [profile_volume(book, volume, resolver) for volume in volumes],
        "css_warnings": sorted(resolver.problems),
    }
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--epub", type=Path, default=EPUB_PATH)
    parser.add_argument("--output", type=Path, default=MD_PATH, help="Markdown report")
    parser.add_argument("--json-output", type=Path, default=JSON_PATH)
    parser.add_argument("--book", help="仅分析目录中的指定分册")
    parser.add_argument(
        "--details-dir",
        type=Path,
        default=Path("data/reports/epub_dom_layout_details"),
        help="每分册详细 Markdown 的输出文件夹",
    )
    args = parser.parse_args()
    book = epub.read_epub(str(args.epub))
    report = run(book, parse_toc(book.toc), args.book)
    for path, content in (
        (args.output, render_overview_md(report)),
        (args.json_output, json.dumps(report, ensure_ascii=False, indent=2)),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        print(f"报告：{path}")

    args.details_dir.mkdir(parents=True, exist_ok=True)
    for index, volume in enumerate(report["volumes"], 1):
        # 每本详细报告保留低频模板全例、样式 run 和连续结构证据。
        one = {"volumes": [volume], "css_warnings": []}
        path = args.details_dir / volume_report_filename(index, volume["volume"])
        path.write_text(render_md(one), encoding="utf-8")
    print(f"分册详细报告：{args.details_dir}（{len(report['volumes'])} 份）")
    print(f"分册：{len(report['volumes'])}；CSS 提醒：{len(report['css_warnings'])}")


if __name__ == "__main__":
    main()
